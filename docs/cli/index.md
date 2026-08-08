# CLI Reference

Five commands. Two of them (`install`, `sync`) you run once when setting a project
up; the rest you use day to day.

| Command | What it does |
|---|---|
| [`hooksmith run`](run.md) | Execute hooks against the changeset. The one you'll use most. |
| [`hooksmith install`](install.md) | Write the git hook scripts that fire `run` on commit/push. |
| [`hooksmith sync`](sync.md) | Build every hook's environment ahead of time. |
| [`hooksmith cache`](cache.md) | Explain (`why`) and reclaim (`clear`) the environment cache. |
| [`hooksmith migrate`](migrate.md) | Convert a `.pre-commit-config.yaml` into a `check.toml`. |

## Global options

```console
$ hooksmith --help
$ hooksmith --version
```

`-h` works everywhere `--help` does.

## Conventions

**`--config`** — every command that reads configuration accepts `--config PATH`. When
omitted, hooksmith searches **upward** from the current directory for a `check.toml`
(or a `pyproject.toml` with `[tool.hooksmith]`), stopping at the repository root — so
commands work from any subdirectory. In a monorepo, the config that's found determines
which workspace root is discovered.

**Exit codes** — `0` means the command achieved what it set out to do; `1` means a
hook failed, an environment could not be built, or the configuration was invalid.
That makes `run` usable directly as a CI gate or a git hook.

**Errors are messages, not tracebacks.** A malformed `check.toml`, a missing tool, an
unknown group or a bad git ref all print a single actionable line. If you ever see a
Python traceback, that's a bug worth reporting.

## A typical session

```bash
hooksmith migrate     # coming from pre-commit? convert first
hooksmith sync        # build the environments
hooksmith install     # wire up the git hooks
hooksmith run         # check what's staged, right now
```

After that, the git hooks run on their own — running `hooksmith run` by hand is for
when you want to check *before* committing.
