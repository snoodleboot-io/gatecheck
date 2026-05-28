# Quick Start

Get gatecheck running in your project in under two minutes.

## Install

```bash
pip install gatecheck
# or with uv (recommended):
uv tool install gatecheck
```

## Create `check.toml`

```bash
# Start fresh:
touch check.toml

# Or migrate from pre-commit:
gatecheck migrate
```

A minimal `check.toml` for a Python project:

```toml
[sources]
default-registry = "https://pypi.org/simple"

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

[group.lint]
hooks    = ["ruff", "ruff-format"]
parallel = true
on-event = "commit"
```

## Install git hooks

```bash
gatecheck install
```

This writes `.git/hooks/pre-commit` (and other hooks based on your `on-event` settings).

## Sync environments

```bash
gatecheck sync
```

Downloads and installs all hook dependencies. First run takes a moment; subsequent runs are instant (cached by uv).

## Run manually

```bash
# Run on staged files (same as what the git hook does)
gatecheck run

# Run a specific group
gatecheck run lint

# Run on all tracked files (good for CI)
gatecheck run --all-files

# Run a single hook
gatecheck run --hook ruff
```

## What it looks like

```
$ git commit -m "feat: add workspace support"

  ✓ ruff          (0.3s)
  ✓ ruff-format   (0.1s)

  2 passed  in 0.4s
```

On failure:

```
$ git commit -m "fix: typo"

  ✓ ruff          (0.3s)
  ✗ ruff-format   (0.1s)

    --- a/src/api.py
    +++ b/src/api.py
    @@ -4,7 +4,7 @@
    -def my_function( x, y ):
    +def my_function(x, y):

  1 passed · 1 failed  in 0.4s
```

## Next steps

- [Configuration reference](../config/reference.md) — full `check.toml` spec
- [Source types](../config/sources.md) — PyPI, private, git, local, Docker
- [Monorepo setup](../guides/monorepo.md) — workspace configs and `--affected`
- [Migration from pre-commit](migration.md) — automated conversion
