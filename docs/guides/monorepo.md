# Monorepo Setup

hooksmith has native workspace support for monorepos. Hooks run only for relevant packages, package dependency graphs propagate affected status, and each package can override hook versions or add package-specific hooks.

## Workspace structure

```
my-monorepo/
├── check.toml              # workspace root — shared hooks + workspace config
├── packages/
│   ├── api/
│   │   ├── check.toml     # package config — inherits root + overrides
│   │   └── src/
│   ├── frontend/
│   │   ├── check.toml     # different stack (Node hooks)
│   │   └── src/
│   └── legacy/
│       ├── check.toml     # pinned to older versions
│       └── src/
└── libs/
    └── shared/
        └── check.toml     # no extra hooks; declared as a dep
```

## Workspace root `check.toml`

```toml
[workspace]
packages = ["packages/*", "libs/*"]  # glob patterns
inherit  = "merge"                    # how child configs relate to root

[sources]
default-registry = "https://pypi.org/simple"

# These hooks run for every package
[[hook]]
id    = "ruff"
from  = "pypi:ruff>=0.4"
run   = "ruff check --fix {files}"
files = "*.py"

[[hook]]
id    = "ruff-format"
from  = "pypi:ruff>=0.4"
run   = "ruff format {files}"
files = "*.py"
depends-on = ["ruff"]

[group.lint]
hooks    = ["ruff", "ruff-format"]
parallel = true
on-event = "commit"
```

## Package config

Each package can add hooks, override root hooks, or declare dependencies:

```toml title="packages/api/check.toml"
[package]
depends-on = ["shared"]   # api depends on the shared lib

# Add a hook only for this package
[[hook]]
id        = "mypy"
from      = "project"
run       = "mypy src/"
pass-files = false

[group.typecheck]
hooks    = ["mypy"]
on-event = "push"
```

```toml title="packages/legacy/check.toml"
[package]
python = "3.9"     # this package uses an older Python

# Override the root ruff hook — legacy isn't clean yet
[[hook]]
id   = "ruff"
from = "pypi:ruff>=0.4"
run  = "ruff check {files}"   # --fix removed intentionally
when = { env = "RUN_RUFF_ON_LEGACY" }

# Use older black instead
[[hook]]
id   = "black"
from = "pypi:black==22.12.0"
run  = "black {files}"
files = "*.py"
```

## Running hooks

### All packages

```bash
hooksmith run              # staged files
hooksmith run --all-files  # all tracked files
hooksmith run lint         # named group, all packages
```

### Affected packages only

```bash
# Only run for packages containing changed files (+ their dependents)
hooksmith run --affected --base main
```

This is the key monorepo feature. If `shared` changed and `api` declares `depends-on = ["shared"]`, both `shared` and `api` are included — even if no files in `api/` changed.

```bash
$ hooksmith run --affected --base main

  Affected packages: shared, api

  shared
  ✓ ruff          (0.3s)
  ✓ ruff-format   (0.1s)
  2 passed in 0.4s

  api
  ✓ ruff          (0.3s)
  ✓ ruff-format   (0.1s)
  ✓ mypy          (4.1s)
  3 passed in 4.5s
```

### Specific package

Run from inside the package directory — hooksmith discovers that package's
`check.toml`:

```bash
cd packages/api && hooksmith run
```

## Dependency graph

The `depends-on` field in `[package]` declares which other packages this package depends on. hooksmith uses this to propagate affected status upward through the graph.

```
libs/shared ←── packages/api ←── packages/worker
                       ↑
              packages/frontend
```

If `shared` changes → `api`, `frontend`, and `worker` are all affected.
If `api` changes → `worker` is affected (but not `shared` or `frontend`).
If `frontend` changes → only `frontend` is affected.

### Root-level changes

A changed file that lives under **no** package directory is treated as a shared/root
change — the root `check.toml`, a top-level lockfile (`uv.lock`), CI config, or any
shared tooling. Such a change conservatively marks **every** package affected, since a
shared file can influence all of them. Over-running is safe; silently skipping a
package that a root change actually broke is not.

## Environment sharing

When 10 packages all declare `from = "pypi:ruff>=0.4"`, hooksmith resolves this to the same cache key and uses a single shared venv. The lockfile at the workspace root tracks this globally.

## Seeing which packages ran

There is no separate introspection command — `hooksmith run --affected` reports the
packages it selected, prefixing each result with the package name:

```bash
$ hooksmith run --affected --base main

ok    shared:ruff  (0.31s)
ok    shared:mypy  (1.04s)
ok    api:ruff     (0.28s)

3 passed
```

Pair it with `--json` when you need the selection programmatically — each
`results[].hook_id` carries the `<package>:<hook>` prefix:

```bash
hooksmith run --affected --base main --json | jq -r '.results[].hook_id'
```

## CI integration

```yaml title=".github/workflows/ci.yml (excerpt)"
- name: Run affected checks
  run: |
    hooksmith run --affected --base ${{ github.event.pull_request.base.sha }} \
                  --all-files \
                  --json | tee hooksmith-results.json

- name: Annotate PR with failures
  if: failure()
  run: |
    cat hooksmith-results.json | python scripts/annotate_pr.py
```
