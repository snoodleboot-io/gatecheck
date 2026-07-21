# Why Not pre-commit?

pre-commit is a well-maintained, widely adopted tool that has served the Python community since 2014. This document isn't a takedown — it's an honest accounting of the architectural decisions that made sense in 2014 and that limit what's possible today.

## The fundamental constraints

### 1. GitHub URLs as the only hook source

pre-commit requires hooks to be published as git repositories, typically on GitHub:

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
```

This was a reasonable decision when pre-commit launched: it gave hook authors a place to publish hooks without needing PyPI packaging, and it gave pre-commit a stable identifier for each hook version.

The consequences ten years later:

- **You cannot install hooks from PyPI**, even when the hook is a published package (black, ruff, mypy, isort — all on PyPI, all requiring GitHub URLs in pre-commit).
- **Private hooks require private GitHub** (or GitLab/Bitbucket workarounds). If your org publishes internal tools to a private PyPI, they're second-class citizens.
- **Semver ranges are impossible**. `rev: 24.3.0` is a git tag. There is no `rev: ">=24,<25"`.
- **The "local" hook special-case** exists specifically to paper over this limitation, but local hooks lose most of the isolation guarantees.

gatecheck treats source type as a URI scheme: `pypi:black>=24`, `pypi+internal:my-linter==1.0`, `git:https://github.com/org/repo@v2`, `local:scripts/check.py`, `docker:ghcr.io/org/linter:latest`. All are first-class.

### 2. One venv per hook, always

pre-commit creates an isolated virtualenv for every hook. This is safe but expensive:

- `ruff`, `black`, `isort` — each gets its own venv even though they're all Python tools that don't conflict.
- If you have 10 hooks, you have 10 venvs sitting in `~/.cache/pre-commit`.
- Your project's venv (the one with your actual dependencies) is never used — even for `mypy`, which needs your project's types to work correctly.

The `from = "project"` source type in gatecheck solves the mypy problem directly: run the hook inside the existing project venv. No shadow copies, no version drift between what mypy sees and what your project actually uses.

The `from = "shared:group-name"` mode (roadmap) lets hooks that share compatible dependencies pool into a single env — one ruff install for 50 packages in a monorepo.

### 3. No monorepo awareness

pre-commit has no concept that a repository might contain multiple packages. You get one `.pre-commit-config.yaml` at the root. If you run a hook that's only relevant to Python code, it will happily attempt to run on your Rust crate, your TypeScript frontend, and your Helm charts.

Workarounds exist:
- `files:` and `exclude:` patterns — brittle path regexes
- Multiple `.pre-commit-config.yaml` files invoked by a wrapper script — not supported natively
- Running pre-commit per-package in CI — loses the "one command" UX

gatecheck's workspace model is first-class:

```
check.toml          ← workspace root (shared hooks, workspace config)
packages/
  api/check.toml   ← inherits root, adds mypy, declares depends-on: [shared]
  frontend/check.toml  ← different stack entirely (Node hooks)
  legacy/check.toml   ← pinned to older versions
libs/
  shared/check.toml   ← the dep that everything else depends on
```

`gatecheck run --affected --base main` diffs against main, maps changed files to packages, propagates through the dependency graph (if `shared` changed, also run `api` and `frontend`), and runs only what needs running.

### 4. Sequential execution by default

pre-commit runs hooks one at a time in list order. If `ruff` takes 2s, `mypy` takes 8s, and `black` takes 1s — you wait 11 seconds sequentially even though none of them depend on each other.

gatecheck builds a DAG from `depends-on` declarations and executes independent hooks in parallel using rayon's thread pool. The three hooks above run in ~8s (mypy dominates, ruff and black run alongside it).

### 5. Opaque cache invalidation

When does pre-commit rebuild a hook's environment? The answer involves inspecting the source in `~/.cache/pre-commit`, understanding its internal hash format, and hoping the invalidation logic matches your mental model.

`gatecheck cache why black` tells you exactly:

```
$ gatecheck cache why black
Source changed: was 'pypi:black==23.9.1', now 'pypi:black==24.3.0'.
Env at ~/.cache/gatecheck/envs/pypi_a3f8b2c1d4e5f6a7 will be rebuilt.
```

`gatecheck cache why <hook>` explains any hook's cache key and hit/miss status (`--json` for machine consumption). `gatecheck cache clear` removes cached environments, reporting how many and how much space was freed — `--dry-run` previews, `--all` also drops the bootstrapped `uv`.

### 6. Config verbosity

```yaml
# pre-commit: 8 lines for one hook
repos:
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
        language_version: python3.11
```

```toml
# gatecheck: 3 lines for the same hook
[[hook]]
id   = "black"
from = "pypi:black==24.3.0"
```

The `repos:` / `hooks:` nesting in pre-commit exists because the data model is "a collection of repositories, each of which contains hooks." gatecheck's data model is "a flat list of hooks, each of which declares its source." The nesting reflects the implementation, not the intent.

## What pre-commit does well

To be clear: pre-commit's approach to git hook installation, its hook repository ecosystem, and its `--all-files` / staged-file semantics are all good and worth preserving. gatecheck keeps all of these:

- `gatecheck install` installs git hooks the same way
- Hooks run on staged files by default, `--all-files` for CI
- `gatecheck migrate` converts your existing `.pre-commit-config.yaml`

The migration path is intentional. Switching to gatecheck shouldn't require rewriting your entire hook setup from scratch.

## The Rust question

See [Rust Core](rust-core.md) for the full treatment. The short version: the runner, DAG solver, and file-matching logic are in Rust not because Python is slow, but because:

1. The startup time matters — a 300ms no-op on every commit is noticeable
2. The parallel executor is where Rust's ownership model prevents races without a GIL
3. Distributing as a compiled maturin wheel means users never see the Rust — they just `pip install gatecheck` and get a fast binary
