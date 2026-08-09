# `hooksmith install`

Write the git hook scripts that make hooksmith run automatically.

```console
$ hooksmith install [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--config FILE` | discovered | Path to the config. Default: found by searching upward for `check.toml` or a `[tool.hooksmith]` `pyproject.toml`. |

## What it installs

Only groups that declare an [`on-event`](../config/groups.md) are wired up. Each
event maps to one git hook file:

| `on-event` | git hook |
|---|---|
| `commit` | `.git/hooks/pre-commit` |
| `push` | `.git/hooks/pre-push` |
| `commit-msg` | `.git/hooks/commit-msg` |

Several groups can target the same event; they're written into that one hook file in
declared order.

```toml title="check.toml"
[group.format]
hooks    = ["ruff-format"]
on-event = "commit"

[group.lint]
hooks    = ["ruff", "mypy"]
on-event = "commit"

[group.full]
hooks    = ["ruff", "mypy", "tests"]
on-event = "push"

[group.msg]
hooks    = ["conventional-commit"]
on-event = "commit-msg"
```

```console
$ hooksmith install
installed  pre-commit  (format, lint)
installed  pre-push    (full)
installed  commit-msg  (msg)
```

The generated script is deliberately boring:

```sh title=".git/hooks/pre-commit"
#!/bin/sh
# hooksmith-managed
set -e
hooksmith run format
hooksmith run lint
```

The `commit-msg` script forwards git's message-file argument (`$1`) so the group's
hooks can inspect the pending message via [`{commit-msg}`](run.md#message-check-mode):

```sh title=".git/hooks/commit-msg"
#!/bin/sh
# hooksmith-managed
set -e
hooksmith run msg --commit-msg-file "$1"
```

`set -e` means the first failing group stops the commit, and the non-zero exit
propagates to git.

## It won't clobber your existing hooks

Every generated script carries a `# hooksmith-managed` marker on its second line.
On install:

- **No hook file** → written.
- **A hooksmith-managed hook** → overwritten (this is how you pick up config changes).
- **Any other hook** → left completely untouched, and reported as skipped.

```console
$ hooksmith install
installed  pre-commit  (lint)
skipped    pre-push    — existing hook is not hooksmith-managed
```

That last line is not an error — it's telling you a hook you wrote by hand is still
there. Move its contents into `check.toml`, or delete the file and re-run, whichever
you prefer.

## Nothing to install

```console
$ hooksmith install
Nothing to install — no group declares an 'on-event'.
```

Hooks still work; you just have to invoke `hooksmith run` yourself. Add `on-event` to
a group when you want it automatic.

## Re-running it

`install` is idempotent — run it again whenever you add, remove or re-point a group.
It rewrites the managed hooks from the current `check.toml` and leaves everything else
alone.

## Uninstalling

There's no `uninstall` command. The hooks are ordinary files:

```bash
rm .git/hooks/pre-commit .git/hooks/pre-push
```

Check for the `# hooksmith-managed` marker first if you're not sure whether a hook is
one of ours.

## Skipping hooks temporarily

Use git's own escape hatch — hooksmith doesn't need to know:

```bash
git commit --no-verify
```

For a single hook, prefer a [`when` condition](../config/conditions.md) such as
`when = { env-not = "SKIP_MYPY" }`, so it's explicit and reviewable.

## See also

- [`hooksmith sync`](sync.md) — build the environments before the first commit, so
  the hook isn't slow the first time it fires.
- [Groups & Ordering](../config/groups.md) — `on-event`, `fail-fast`, `parallel`.
