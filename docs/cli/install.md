# `gatecheck install`

Write the git hook scripts that make gatecheck run automatically.

```console
$ gatecheck install [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `--config FILE` | `check.toml` | Path to the configuration file. |

## What it installs

Only groups that declare an [`on-event`](../config/groups.md) are wired up. Each
event maps to one git hook file:

| `on-event` | git hook |
|---|---|
| `commit` | `.git/hooks/pre-commit` |
| `push` | `.git/hooks/pre-push` |

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
```

```console
$ gatecheck install
installed  pre-commit  (format, lint)
installed  pre-push    (full)
```

The generated script is deliberately boring:

```sh title=".git/hooks/pre-commit"
#!/bin/sh
# gatecheck-managed
set -e
gatecheck run format
gatecheck run lint
```

`set -e` means the first failing group stops the commit, and the non-zero exit
propagates to git.

## It won't clobber your existing hooks

Every generated script carries a `# gatecheck-managed` marker on its second line.
On install:

- **No hook file** → written.
- **A gatecheck-managed hook** → overwritten (this is how you pick up config changes).
- **Any other hook** → left completely untouched, and reported as skipped.

```console
$ gatecheck install
installed  pre-commit  (lint)
skipped    pre-push    — existing hook is not gatecheck-managed
```

That last line is not an error — it's telling you a hook you wrote by hand is still
there. Move its contents into `check.toml`, or delete the file and re-run, whichever
you prefer.

## Nothing to install

```console
$ gatecheck install
Nothing to install — no group declares an 'on-event'.
```

Hooks still work; you just have to invoke `gatecheck run` yourself. Add `on-event` to
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

Check for the `# gatecheck-managed` marker first if you're not sure whether a hook is
one of ours.

## Skipping hooks temporarily

Use git's own escape hatch — gatecheck doesn't need to know:

```bash
git commit --no-verify
```

For a single hook, prefer a [`when` condition](../config/conditions.md) such as
`when = { env-not = "SKIP_MYPY" }`, so it's explicit and reviewable.

## See also

- [`gatecheck sync`](sync.md) — build the environments before the first commit, so
  the hook isn't slow the first time it fires.
- [Groups & Ordering](../config/groups.md) — `on-event`, `fail-fast`, `parallel`.
