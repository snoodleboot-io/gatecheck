# Monorepo / Workspace

In a monorepo, the root `check.toml` declares a workspace and each package may carry
its own `check.toml` that inherits from it.

```toml title="check.toml (workspace root)"
[workspace]
packages = ["packages/*", "libs/*"]
inherit  = "merge"

[[hook]]
id    = "ruff"
from  = "pypi:ruff==0.4.9"
run   = "ruff check --fix {files}"
files = "*.py"
```

```toml title="packages/api/check.toml"
[package]
depends-on = ["shared"]

[[hook]]
id         = "mypy"
from       = "project"
run        = "mypy src/"
pass-files = false
```

`packages/api` gets `ruff` from the root **and** its own `mypy`.

---

## `[workspace]`

Only valid in the root config.

| Field | Type | Default | Description |
|---|---|---|---|
| `packages` | list of globs/paths | *required*, non-empty | Package directories |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | `"merge"` | Default relationship to the root config |

```toml
packages = ["packages/*", "libs/*", "services/api"]
```

Entries are globs or literal paths relative to the root. A directory is a package when
it matches and contains a `check.toml`. The package's **name** is its directory name.

## `[package]`

Only valid in a package's own config.

| Field | Type | Default | Description |
|---|---|---|---|
| `depends-on` | list of names | `[]` | Packages this one depends on |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | workspace default | Override the inherit mode here |
| `python` | string | — | Interpreter for this package's `pypi:` environments |

The `python` version is passed to `uv venv --python <version>` when building this
package's `pypi:` hook environments, and it's part of the environment cache key — so
two packages pinning different interpreters get separate venvs rather than colliding.
`project` / `system` hooks are unaffected (they reuse an existing binary), and a tool
that's interpreter-agnostic (ruff, say) won't behave differently, but a package that
genuinely needs a specific interpreter for its isolated tools gets it.

---

## Inheritance modes

How a package's config combines with the root's:

=== "`merge` (default)"

    Root hooks and groups apply, with the package layered on top. A package hook
    sharing an id with a root hook **replaces** it.

    ```toml
    # root: ruff, mypy      package: mypy (stricter), tests
    # effective: ruff, mypy (the package's), tests
    ```

    Use this for a shared baseline plus per-package additions. It's the default
    because it's what most monorepos want.

=== "`override`"

    The package config replaces the root entirely — no root hooks apply.

    ```toml
    [package]
    inherit = "override"
    ```

    Use for a package with a genuinely different stack: a Go service or a frontend
    inside an otherwise-Python repo.

=== "`none`"

    The package is standalone; root hooks do not apply to it.

    Practically similar to `override`, but states the intent differently: `override`
    means "I'm replacing the baseline", `none` means "the baseline was never meant
    for me".

Set the default in `[workspace].inherit`, and override per package in
`[package].inherit`.

---

## The dependency graph

`depends-on` names other packages, and drives `--affected`:

```toml title="packages/api/check.toml"
[package]
depends-on = ["shared"]
```

```
libs/shared ←── packages/api ←── packages/worker
                      ↑
             packages/frontend
```

- Change `shared` → `api`, `worker` and `frontend` are all affected.
- Change `api` → `worker` is affected; `shared` is not (it's a dependency, not a dependent).
- Change `frontend` → only `frontend`.

Affectedness propagates **to dependents**, transitively. A `depends-on` naming an
unknown package, or a cycle, is a config error.

### Root-level changes affect everything

A changed file that lives under **no** package — the root `check.toml`, a lockfile, CI
config, shared tooling — conservatively marks **every** package affected. A shared file
can influence all of them, and for a checker, over-running is safe while silently
skipping a package the change actually broke is not.

---

## Running

```bash
gatecheck run --affected --base main
```

Results are prefixed with the package name:

```console
ok    shared:ruff  (0.31s)
ok    shared:mypy  (1.04s)
ok    api:ruff     (0.28s)

3 passed
```

Each package's hooks run with that package's directory as the working directory, and
receive only that package's changed files. Environments are still shared globally — ten
packages pinning `ruff==0.4.9` build one venv between them, because the cache key is
content-addressed on the package, not the project path.

There is no separate `workspace` command; `run --affected` is the whole interface. Add
`--json` when you want the selection programmatically.

## See also

- [Monorepo Setup](../guides/monorepo.md) — the task-shaped walkthrough.
- [`gatecheck run`](../cli/run.md) — `--affected`, `--base`, `--json`.
