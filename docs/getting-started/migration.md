# Migration from pre-commit

gatecheck ships with an automated migration command that converts your `.pre-commit-config.yaml` to `check.toml`.

## Automated migration

```bash
gatecheck migrate
```

This reads `.pre-commit-config.yaml` in the current directory and writes `check.toml`. Review the output before committing.

```bash
# Specify paths explicitly
gatecheck migrate --input .pre-commit-config.yaml --output check.toml

# Write somewhere else to diff before adopting
gatecheck migrate --output check.toml.new
```

`migrate` never edits your `.pre-commit-config.yaml`, and it prints a warning for
every hook it could not translate confidently — nothing is silently dropped.

## What gets converted

### Remote repos → PyPI sources

The migrator has a built-in map of well-known GitHub repos to their gatecheck sources:

| pre-commit repo | gatecheck source | run |
|---|---|---|
| `astral-sh/ruff-pre-commit` | `pypi:ruff` | `ruff check` / `ruff format` |
| `psf/black` (and `black-pre-commit-mirror`) | `pypi:black` | `black` |
| `pycqa/isort` | `pypi:isort` | `isort` |
| `pycqa/flake8` | `pypi:flake8` | `flake8` |
| `pycqa/bandit` | `pypi:bandit` | `bandit` |
| `pycqa/pydocstyle` · `pycqa/autoflake` · `pycqa/docformatter` | `pypi:<tool>` | `<tool>` |
| `pre-commit/mirrors-mypy` | `pypi:mypy` | `mypy` |
| `pre-commit/pre-commit-hooks` | `pypi:pre-commit-hooks` | the hook id (each hook is its own script) |
| `codespell-project/codespell` | `pypi:codespell` | `codespell` |
| `Yelp/detect-secrets` | `pypi:detect-secrets` | `detect-secrets` |
| `asottile/pyupgrade` · `asottile/add-trailing-comma` | `pypi:<tool>` | `<tool>` |
| `shellcheck-py/shellcheck-py` | `pypi:shellcheck-py` | `shellcheck` |
| `mirrors-prettier` · `mirrors-eslint` · `koalaman/shellcheck-precommit` | `system` (must be on `PATH`) + warning | `prettier` / `eslint` / `shellcheck` |
| Unknown repos | `pypi:<guessed-name>` with a warning | the hook `entry`/id |

Node/system tools (prettier, eslint, shellcheck-precommit) have no PyPI package, so they map to `from = "system"` and gatecheck expects them already on your `PATH` — the migrator emits a warning for each.

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
