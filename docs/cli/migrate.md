# `gatecheck migrate`

Convert a `.pre-commit-config.yaml` into a `check.toml`.

```console
$ gatecheck migrate [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--input FILE` | `.pre-commit-config.yaml` | The pre-commit config to read. |
| `--output FILE` | `check.toml` | Where to write the converted config. |

```console
$ gatecheck migrate
warning: hook 'prettier': maps to system tool 'prettier' — ensure it is installed on PATH (gatecheck does not manage npm/system tools)
warning: hook 'custom': best-effort mapping for unknown repo 'https://github.com/acme/custom-linter' (from = 'pypi:custom-linter')
Wrote check.toml
```

`migrate` never modifies your `.pre-commit-config.yaml`. Keep both files side by side
until you're satisfied, then delete the old one.

## The contract: nothing is silently dropped

Every hook in the input produces a hook in the output. Where the translation is
uncertain, gatecheck still emits the hook and prints a **warning** saying what it
guessed. Read the warnings, fix what matters, delete what doesn't.

That's the whole design: a migration you have to review is honest; one that silently
drops what it couldn't handle is not.

## What gets translated

**Known repos** map to a real source and run command:

| pre-commit repo | `from` | `run` |
|---|---|---|
| `astral-sh/ruff-pre-commit` | `pypi:ruff` | `ruff check` / `ruff format` |
| `psf/black` (and the mirror) | `pypi:black` | `black` |
| `pycqa/isort` · `flake8` · `bandit` · `pydocstyle` · `autoflake` · `docformatter` | `pypi:<tool>` | `<tool>` |
| `pre-commit/mirrors-mypy` | `pypi:mypy` | `mypy` |
| `pre-commit/pre-commit-hooks` | `pypi:pre-commit-hooks` | the hook id (each is its own script) |
| `codespell-project/codespell` | `pypi:codespell` | `codespell` |
| `Yelp/detect-secrets` | `pypi:detect-secrets` | `detect-secrets` |
| `asottile/pyupgrade` · `add-trailing-comma` | `pypi:<tool>` | `<tool>` |
| `shellcheck-py/shellcheck-py` | `pypi:shellcheck-py` | `shellcheck` |
| `mirrors-prettier` · `mirrors-eslint` · `koalaman/shellcheck-precommit` | `system` **+ warning** | `prettier` / `eslint` / `shellcheck` |
| anything else | `pypi:<guessed-name>` **+ warning** | the hook `entry`, else its id |

**`rev` → a version pin.** `rev: v0.4.9` becomes `pypi:ruff==0.4.9`. A rev that isn't
a version — a git sha, a moving tag — can't be pinned, so you get an unpinned source
and a warning. Pin it by hand; it's also what [offline mode](../guides/air-gapped.md)
needs.

**`args`** are appended to the run command.

**`pass_filenames: false`** becomes `pass-files = false`.

**`files`** is a *regex* in pre-commit and a *glob* in gatecheck. The common
single-extension form translates cleanly:

| pre-commit | check.toml |
|---|---|
| `\.py$` · `^\.py$` · `.*\.py$` | `files = "*.py"` |
| `\.(py\|pyi)$`, `^src/.*_test\.py$`, … | left out, **+ warning** |

Anything with alternation, character classes or path anchors is not safely a single
glob, so it isn't guessed at.

**`repo: local`** becomes `from = "system"`, running the hook's `entry` as written.

**Duplicate ids** are de-duplicated: a second `black` becomes `black-2`.

## What doesn't carry over

Groups, `depends-on`, `on-event` and `when` conditions have no pre-commit equivalent —
they're what you add *after* migrating to get parallelism and ordering. The output is
a flat list of hooks; see [Groups & Ordering](../config/groups.md) for the next step.

`language_version`, `stages`, `additional_dependencies` and other pre-commit keys are
read but not translated.

## Reviewing before you commit

Write somewhere else and diff:

```bash
gatecheck migrate --output check.toml.new
diff check.toml check.toml.new
```

Then check the result actually works before deleting anything:

```bash
gatecheck sync                 # do the environments build?
gatecheck run --all-files      # does everything still pass?
```

Only then:

```bash
pre-commit uninstall
rm .pre-commit-config.yaml
gatecheck install
```

## See also

- [Migration from pre-commit](../getting-started/migration.md) — the fuller walkthrough.
- [Why not pre-commit](../design/why-not-precommit.md) — what you gain by moving.
