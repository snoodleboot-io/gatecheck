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

---

## Python API

For tools that need to consume `check.toml` programmatically, `gatecheck.config.load_config` is the entry point. It returns a fully validated `GatecheckConfig` object built from four pydantic models that mirror the documented schema. The function is synchronous and side-effect-free beyond reading the file.

```python
from pathlib import Path
from gatecheck.config import load_config

cfg = load_config(Path("check.toml"))
for hook in cfg.hook:
    print(hook.id, hook.from_, hook.run)
for name, group in cfg.group.items():
    print(name, group.hooks, group.parallel)
```

The package exposes exactly seven public symbols, all re-exported from `gatecheck.config`:

| Symbol | Kind | Source module |
|---|---|---|
| `ConfigError` | exception | `gatecheck.config.config_error` |
| `GatecheckConfig` | pydantic model | `gatecheck.config.gatecheck_config` |
| `GroupDef` | pydantic model | `gatecheck.config.group_def` |
| `HookDef` | pydantic model | `gatecheck.config.hook_def` |
| `SourceSpec` | pydantic model | `gatecheck.config.source_spec` |
| `dump_config` | function | `gatecheck.config.dumper` |
| `load_config` | function | `gatecheck.config.loader` |

### `dump_config`

```python
from gatecheck.config import dump_config

dump_config(config: GatecheckConfig, path: Path) -> None
```

Serialize a `GatecheckConfig` back to a valid `check.toml` file at `path`. Complements `load_config` — where `load_config` reads and validates a TOML file into a typed model, `dump_config` writes a typed model back to a TOML file.

#### Round-trip contract

`dump_config` and `load_config` are inverses of each other:

```python
from pathlib import Path
from gatecheck.config import dump_config, load_config

original = load_config(Path("check.toml"))
dump_config(original, Path("check.copy.toml"))
copy = load_config(Path("check.copy.toml"))
assert original == copy  # round-trip fidelity
```

Any `GatecheckConfig` produced by `load_config` can be passed to `dump_config`, and the resulting file will produce an equal `GatecheckConfig` when loaded again.

#### Field omission

Fields are omitted from the output when their value is `None` or when their value equals the pydantic-declared default for that field. This keeps the output clean and human-editable — only fields with meaningful, non-default values appear in the file.

Examples of omitted fields: `pass-files = true` (default is `true`), `depends-on = []` (default is empty list), `when` when no conditions are set.

#### TOML structure

The output uses the same idiomatic TOML constructs as a hand-written `check.toml`:

- `[[hook]]` — each hook is emitted as an array-of-tables block.
- `[group.<name>]` — each group uses a dotted-table header.
- `when = { … }` — conditional execution is serialized as an inline table, never a sub-table.

Sections whose data is absent (`hook` list empty, `group` dict empty, `sources` is `None`) are not written to the output at all.

TOML key names use hyphens (`pass-files`, `depends-on`, `from`, `on-event`, `fail-fast`, `env-not`, `on-ci`, `default-registry`), matching the canonical `check.toml` format.

#### Errors

`dump_config` is synchronous and side-effect-free beyond writing `path`. The following OS errors propagate unchanged — no new exception types are introduced:

| Exception | Cause |
|---|---|
| `IsADirectoryError` (or `OSError`) | `path` is an existing directory |
| `FileNotFoundError` | `path`'s parent directory does not exist |
| `PermissionError` | `path` is not writable |

#### Example

```python
from pathlib import Path
from gatecheck.config import GatecheckConfig, HookDef, dump_config

cfg = GatecheckConfig(
    hook=[
        HookDef(**{"id": "ruff", "from": "pypi:ruff>=0.4", "run": "ruff check --fix {files}", "files": "*.py"}),
    ]
)
dump_config(cfg, Path("check.toml"))
```

The above produces:

```toml
[[hook]]
id = "ruff"
from = "pypi:ruff>=0.4"
run = "ruff check --fix {files}"
files = "*.py"
```

Note that `pass-files` is absent because its value (`true`) equals the default.

---

### Error handling

`load_config` raises `gatecheck.config.ConfigError` for any config-shape problem — malformed TOML or a schema violation. `ConfigError` subclasses `ValueError`, so existing `except ValueError:` callers continue to work without changes.

#### `ConfigError` format

`str(exc)` is one line per error in the IDE-parseable form `path:line:col: message`, with multiple errors joined by `\n`. This matches the convention used by compilers, `ruff`, `mypy`, and similar tools, so the output works directly with IDE error matchers, vim's quickfix list, and grep/sed pipelines.

A full line looks like:

```
check.toml:5:3: Field required (field: hook.0.id)
```

#### Example

```python
from pathlib import Path
from gatecheck.config import ConfigError, load_config

try:
    cfg = load_config(Path("check.toml"))
except ConfigError as exc:
    for line in str(exc).splitlines():
        print(line)
```

#### Underlying exception identity

`ConfigError` is raised with PEP 3134 exception chaining, so `exc.__cause__` is the original `tomllib.TOMLDecodeError` (malformed TOML) or `pydantic.ValidationError` (schema violation). Callers that need programmatic access to the raw exception — for example, `pydantic.ValidationError.errors()` for structured error data — can read it directly off `__cause__`:

```python
import pydantic
from gatecheck.config import ConfigError, load_config

try:
    cfg = load_config(Path("check.toml"))
except ConfigError as exc:
    if isinstance(exc.__cause__, pydantic.ValidationError):
        for err in exc.__cause__.errors():
            ...  # structured handling
```

#### Errors that are NOT wrapped

Errors raised before TOML parsing propagate as their native exception types and are NOT wrapped in `ConfigError`:

- `FileNotFoundError` — `path` does not exist.
- `PermissionError` — `path` exists but cannot be opened for reading.
- `OSError` — `path` is not a regular file, or exceeds the 1 MiB size cap.

### TOML aliases

TOML keys idiomatically use hyphens, but Python identifiers cannot. Every hyphenated key (`pass-files`, `depends-on`, `on-event`, `fail-fast`, `env-not`, `on-ci`, `default-registry`) maps to an underscored Python attribute (`pass_files`, `depends_on`, `on_event`, etc.). The reserved-word case `from` maps to `from_`. Because each model sets `populate_by_name=True`, both forms work at construction time:

```python
from gatecheck.config import HookDef

HookDef(**{"id": "ruff", "from": "pypi:ruff", "run": "ruff check"})
```
