# check.toml Reference

gatecheck is configured via `check.toml` in the project root, or via `[tool.gatecheck]` in `pyproject.toml`. In a monorepo, each package can have its own `check.toml` that inherits from the workspace root.

## File lookup order

gatecheck searches upward from the current directory for:

1. `check.toml`
2. `pyproject.toml` (must contain `[tool.gatecheck]`)

## Top-level sections

| Section | Description |
|---|---|
| `[sources]` | Registry configuration |
| `[[hook]]` | Hook definitions (array of tables) |
| `[group.<name>]` | Named execution groups |
| `[workspace]` | Monorepo / workspace settings |
| `[package]` | Per-package settings (in package-level configs) |

---

## `[sources]`

```toml
[sources]
default-registry = "https://pypi.org/simple"  # default
extra-registries = [
  { internal = "https://pkg.example.com/simple" },
]
```

| Field | Type | Default | Description |
|---|---|---|---|
| `default-registry` | string | PyPI | Index URL for `pypi:` sources |
| `extra-registries` | list of `{alias = url}` | `[]` | Named private indexes |

---

## `[[hook]]`

Each `[[hook]]` table defines one hook. The double brackets mean it's an array — multiple `[[hook]]` blocks are collected in order.

### Required fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Unique identifier. Used in group references and CLI (`--hook id`). |
| `from` | string | Source spec — see [Source Types](sources.md). |
| `run` | string | Command to execute. `{files}` is replaced with matching staged files. |

### Optional fields

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string | same as `id` | Human-readable display name |
| `pass-files` | bool | `true` | Whether to append matching files to the command |
| `files` | string | (all) | Glob pattern — only files matching this pattern are passed |
| `exclude` | string | (none) | Glob pattern — files matching this are excluded |
| `depends-on` | list of strings | `[]` | Hook IDs this hook must run after |
| `fail-fast` | bool | `false` | Stop all hooks if this one fails |
| `packages` | list of strings | (all) | Workspace: restrict this hook to specific packages |
| `when` | inline table | (always) | Conditional execution — see below |

### `when` conditions

All conditions are AND-ed. A hook only runs when all present conditions pass.

```toml
[[hook]]
id = "mypy"
from = "project"
run = "mypy src/"
when = { env-not = "SKIP_MYPY", branch-not = "release/*" }
```

| Key | Type | Description |
|---|---|---|
| `branch` | string | Exact branch name match |
| `branch-not` | string | Exact branch name exclusion |
| `branch-matches` | string | Regex match against branch name |
| `files-match` | glob | Only run if at least one staged file matches |
| `env` | string | Only run if this env var is set |
| `env-not` | string | Skip if this env var is set |
| `on-ci` | bool | `true` = CI only, `false` = never on CI |

CI is detected via `CI` or `GITHUB_ACTIONS` environment variables.

### Full hook example

```toml
[[hook]]
id          = "mypy"
name        = "Type checker"
from        = "project"
run         = "mypy src/ --config-file mypy.ini"
pass-files  = false
depends-on  = ["ruff"]
fail-fast   = false
packages    = ["api", "worker"]   # workspace only
when = {
  env-not       = "SKIP_MYPY",
  branch-not    = "release/*",
  on-ci         = false
}
```

---

## `[group.<name>]`

Groups are named collections of hooks with execution settings.

```toml
[group.lint]
hooks     = ["ruff", "ruff-format", "isort"]
parallel  = true
fail-fast = true
on-event  = "commit"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `hooks` | list of strings | required | Hook IDs to include |
| `parallel` | bool | `false` | Run all hooks in this group concurrently |
| `fail-fast` | bool | `true` | Stop after first failure |
| `max-workers` | int | 4 | Thread pool size when `parallel = true` |
| `on-event` | string | (none) | Git event: `"commit"`, `"push"`, `"commit-msg"`, `"merge"` |

When `on-event` is set and `gatecheck install` is run, this group is automatically wired to the corresponding git hook.

---

## `[workspace]`

Present only in the workspace root config (top-level monorepo).

```toml
[workspace]
packages = ["packages/*", "libs/*", "services/api"]
inherit  = "merge"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `packages` | list of globs/paths | required | Package directories to include |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | `"merge"` | How package configs relate to root |

### Inheritance modes

- **`merge`** — package config layered on top of root. Child hooks with the same `id` override parent hooks. Groups are merged the same way.
- **`override`** — package config replaces root entirely. Use when a package has a completely different tool stack.
- **`none`** — package config is standalone. Root hooks do not run for this package.

---

## `[package]`

Present only in package-level configs (inside a workspace package directory).

```toml
[package]
depends-on = ["shared", "utils"]
python     = "3.9"
inherit    = "merge"
```

| Field | Type | Default | Description |
|---|---|---|---|
| `depends-on` | list of strings | `[]` | Package names this package depends on. Used by `--affected` to propagate execution to downstream packages when a dependency changes. |
| `python` | string | (workspace default) | Python version for this package's isolated envs |
| `inherit` | `"merge"` \| `"override"` \| `"none"` | workspace default | Per-package override of the workspace inherit mode |

---

## Source spec syntax

The `from` field accepts a URI-style source spec:

| Spec | Example | Description |
|---|---|---|
| `pypi:<spec>` | `pypi:ruff>=0.4,<1` | Public PyPI, semver range supported |
| `pypi+<alias>:<spec>` | `pypi+internal:my-linter==1.0` | Private registry (alias from `[sources]`) |
| `project` | `project` | Use the project's own activated venv |
| `local:<path>` | `local:scripts/lint.py` | Local script or local package |
| `git:<url>[@ref]` | `git:https://github.com/org/repo@v2.1` | Git repo at a tag or commit |
| `docker:<image>` | `docker:ghcr.io/org/linter:latest` | Docker image |
| `system` | `system` | No env management — raw PATH |

See [Source Types](sources.md) for detailed documentation on each source type.

---

## Complete example

```toml
[sources]
default-registry = "https://pypi.org/simple"
extra-registries = [
  { internal = "https://pkg.example.com/simple" },
]

[[hook]]
id   = "ruff"
from = "pypi:ruff>=0.4"
run  = "ruff check --fix {files}"
files = "*.py"

[[hook]]
id   = "ruff-format"
from = "pypi:ruff>=0.4"
run  = "ruff format {files}"
files = "*.py"
depends-on = ["ruff"]

[[hook]]
id        = "mypy"
from      = "project"
run       = "mypy src/"
pass-files = false
when      = { env-not = "SKIP_MYPY" }

[[hook]]
id   = "private-linter"
from = "pypi+internal:org-linter==2.1.0"
run  = "org-lint {files}"

[[hook]]
id   = "check-secrets"
from = "pypi:detect-secrets"
run  = "detect-secrets audit .secrets.baseline"
pass-files = false
when = { on-ci = true }

[group.format]
hooks     = ["ruff-format"]
parallel  = false
on-event  = "commit"

[group.lint]
hooks     = ["ruff", "mypy"]
parallel  = true
fail-fast = false
on-event  = "commit"

[group.full]
hooks     = ["ruff", "ruff-format", "mypy", "check-secrets"]
parallel  = true
fail-fast = false
on-event  = "push"
```
