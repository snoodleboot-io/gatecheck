# Quick Start

Get hooksmith running in your project in under two minutes.

## Install

```bash
pip install hooksmith
# or with uv (recommended):
uv tool install hooksmith
```

## Create `check.toml`

```bash
# Start fresh:
touch check.toml

# Or migrate from pre-commit:
hooksmith migrate
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
hooksmith install
```

This writes `.git/hooks/pre-commit` (and other hooks based on your `on-event` settings).

## Sync environments

```bash
hooksmith sync
```

Downloads and installs all hook dependencies. First run takes a moment; subsequent runs are instant (cached by uv).

## Run manually

```bash
# Run on staged files (same as what the git hook does)
hooksmith run

# Run a specific group
hooksmith run lint

# Run on all tracked files
hooksmith run --all-files

# Run against everything changed since a branch (good for CI)
hooksmith run --base main

# Machine-readable results
hooksmith run --json
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
