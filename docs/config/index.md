# Configuration

Everything lives in one `check.toml` at the project root.

```toml title="check.toml"
[sources]
default-registry = "https://pypi.org/simple"

[[hook]]
id      = "ruff"
from    = "pypi:ruff==0.4.9"
run     = "ruff check --fix {files}"
files   = "*.py"
exclude = "vendor/*"

[[hook]]
id         = "mypy"
from       = "project"
run        = "mypy src/"
pass-files = false
depends-on = ["ruff"]
when       = { env-not = "SKIP_MYPY" }

[group.lint]
hooks     = ["ruff", "mypy"]
parallel  = true
fail-fast = false
on-event  = "commit"
```

## The five sections

| Section | Purpose | Page |
|---|---|---|
| `[sources]` | Which package indexes to resolve `pypi:` against | [Source Types](sources.md) |
| `[[hook]]` | What to run, where the tool comes from, which files | [Reference](reference.md) |
| `[group.<name>]` | How a set of hooks executes, and on which git event | [Groups & Ordering](groups.md) |
| `[workspace]` | Monorepo package discovery and inheritance | [Monorepo / Workspace](workspace.md) |
| `[package]` | Per-package settings inside a workspace | [Monorepo / Workspace](workspace.md) |

The [check.toml Reference](reference.md) is the exhaustive field-by-field listing. The
other pages are task-shaped: read those first, and use the reference to look up a
specific field.

## Design notes

**Everything is validated at load.** An unknown key is an error, not a warning —
every model is `extra="forbid"`. A typo like `pass_files` (underscore instead of
hyphen) fails immediately with the file, line and column, rather than being silently
ignored until you wonder why files aren't being passed.

**Hyphens in TOML, underscores in Python.** `pass-files`, `depends-on`, `on-event`,
`fail-fast`, `max-workers`, `env-not` — the config uses hyphens throughout, matching
TOML convention.

**Order doesn't matter.** Hooks execute in `depends-on` order, not declaration order;
groups reference hooks by id. Declaration order only breaks ties between hooks that
could otherwise run simultaneously, so output stays deterministic.

## `pyproject.toml`

Config can also live under `[tool.gatecheck]` in `pyproject.toml`, for projects that
prefer a single config file. The schema is identical — just prefix each table:

```toml title="pyproject.toml"
[[tool.gatecheck.hook]]
id    = "ruff"
from  = "pypi:ruff==0.4.9"
run   = "ruff check {files}"
files = "*.py"

[tool.gatecheck.group.lint]
hooks    = ["ruff"]
on-event = "commit"
```

A dedicated `check.toml` takes precedence over `pyproject.toml` when both are present.

## Where the config is found

Commands search **upward** from the current directory (so they work from any
subdirectory), checking each level for a `check.toml`, then a `pyproject.toml` with a
`[tool.gatecheck]` table, and stopping at the repository root. Override with
`--config PATH`. See the [reference](reference.md#locating-the-file).

## Validating your config

There's no separate `validate` command — every command that reads configuration
validates it first, so the fastest check is:

```bash
gatecheck sync        # loads the config and resolves every environment
```

A malformed file gives you a single actionable line with `path:line:col`, not a
traceback.
