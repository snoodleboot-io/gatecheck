# Migration from pre-commit

gatecheck ships with an automated migration command that converts your `.pre-commit-config.yaml` to `check.toml`.

## Automated migration

```bash
gatecheck migrate
```

This reads `.pre-commit-config.yaml` in the current directory and writes `check.toml`. Review the output before committing.

```bash
# Preview without writing
gatecheck migrate --dry-run

# Specify paths
gatecheck migrate --source .pre-commit-config.yaml --output check.toml
```

## What gets converted

### Remote repos → PyPI sources

The migrator has a built-in map of well-known GitHub repos to their PyPI package names:

| pre-commit repo | gatecheck source |
|---|---|
| `https://github.com/psf/black` | `pypi:black` |
| `https://github.com/astral-sh/ruff-pre-commit` | `pypi:ruff` |
| `https://github.com/pycqa/isort` | `pypi:isort` |
| `https://github.com/pycqa/flake8` | `pypi:flake8` |
| `https://github.com/pre-commit/mirrors-mypy` | `pypi:mypy` |
| `https://github.com/Yelp/detect-secrets` | `pypi:detect-secrets` |
| `https://github.com/pre-commit/pre-commit-hooks` | `pypi:pre-commit-hooks` |
| Unknown repos | `git:<url>@<rev>` with a warning |

### Local hooks → `local:` source

```yaml
# Before (pre-commit)
repos:
  - repo: local
    hooks:
      - id: my-check
        language: python
        entry: python scripts/check.py
        pass_filenames: false
```

```toml
# After (gatecheck)
[[hook]]
id         = "my-check"
from       = "local:scripts/check.py"
run        = "python scripts/check.py"
pass-files = false
```

### Types → file globs

```yaml
# Before
hooks:
  - id: black
    types: [python]
```

```toml
# After
[[hook]]
id    = "black"
from  = "pypi:black==24.3.0"
files = "*.py"
```

### Pass filenames → pass-files

```yaml
pass_filenames: false
```

```toml
pass-files = false
```

## Manual review checklist

After running `gatecheck migrate`, review:

1. **Unknown repos** — any repo not in the built-in map is converted to `git:` source with a warning comment. Consider whether a PyPI package exists.

2. **Version pinning** — pre-commit `rev: v24.3.0` becomes `pypi:black==24.3.0`. Decide whether to pin exactly or allow ranges (`>=24,<25`).

3. **`types:` mappings** — complex type expressions may not translate perfectly. Check the `files =` glob matches your intent.

4. **`language_version`** — pre-commit's `language_version: python3.11` has no direct equivalent. Set `from = "pypi:black==24.3.0"` and gatecheck will use the default Python. To pin per-hook Python, see [Private Registries](../guides/private-registries.md).

5. **`additional_dependencies`** — hooks that declared extra deps via `additional_dependencies:` in pre-commit will need those deps added to the `from` spec or handled via a shared env.

## Install new hooks

```bash
# Remove old pre-commit hooks
pre-commit uninstall

# Install gatecheck hooks
gatecheck install

# Sync environments
gatecheck sync
```

## Running alongside pre-commit (transition period)

If you want to validate gatecheck before removing pre-commit:

```bash
# Test gatecheck on all files without installing git hooks
gatecheck run --all-files

# If you're happy, uninstall pre-commit and install gatecheck
pre-commit uninstall
gatecheck install
```
