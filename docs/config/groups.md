# Groups & Ordering

A group is a named set of hooks plus a policy for running them.

```toml
[group.lint]
hooks       = ["ruff", "mypy", "cargo-clippy"]
parallel    = true
max-workers = 4
fail-fast   = false
on-event    = "commit"
```

```bash
gatecheck run lint     # just this group
gatecheck run          # every hook, ignoring groups
```

| Field | Type | Default | Effect |
|---|---|---|---|
| `hooks` | list of ids | *required* | Which hooks, in this order |
| `parallel` | bool | `false` | Concurrent when `true`; **serial** when `false` |
| `max-workers` | int ≥ 1 | `4` | Concurrency cap when `parallel = true` |
| `fail-fast` | bool | `false` | Stop scheduling after the first failure |
| `on-event` | `"commit"` \| `"push"` | — | Which git hook fires this group |

Referencing a hook id that doesn't exist is an error, not a warning. Duplicate ids in
`hooks` are de-duplicated.

---

## Ordering: `depends-on`

Order comes from the hooks themselves, not the group's list:

```toml
[[hook]]
id   = "ruff"
from = "pypi:ruff==0.4.9"
run  = "ruff check --fix {files}"

[[hook]]
id         = "ruff-format"
from       = "pypi:ruff==0.4.9"
run        = "ruff format {files}"
depends-on = ["ruff"]        # fix lint errors before reformatting
```

gatecheck topologically sorts the selected hooks into levels. Hooks with no dependency
between them can run concurrently; a hook waits only for what it actually depends on.

A **cycle** is a config error, reported with the hooks involved. A `depends-on`
pointing at an unknown hook is likewise an error.

### When a dependency doesn't run

If a dependency is skipped — by a `when` condition, or because nothing matched its
glob — its edge simply drops, and the dependent still runs. A hook that didn't execute
imposes no ordering.

That's usually what you want: `ruff-format` shouldn't be blocked just because `ruff`
had no Python files to look at. If a hook genuinely must not run without its
dependency, express that with the same `when` condition on both.

---

## Concurrency

**`parallel = false` (the default) runs the group's hooks one at a time**, still in
dependency order. Predictable, easy to read, and the right default for a commit hook
where output interleaving is confusing.

**`parallel = true`** runs up to `max-workers` hooks at once.

Scheduling is **dynamic**: each hook starts the moment its own dependencies finish,
rather than waiting for a whole "level" to complete. On an uneven graph — one slow
hook alongside several fast ones — that's a real wall-clock win over a barrier-based
scheduler.

```toml
[group.lint]
hooks       = ["ruff", "mypy", "cargo-clippy", "shellcheck"]
parallel    = true
max-workers = 2      # never more than 2 subprocesses at once
```

Raise `max-workers` on a big CI box; lower it if the hooks are memory-hungry or you're
sharing the machine. An all-hooks run (`gatecheck run` with no group) is unbounded.

!!! note "Results stay deterministic"

    Hooks may finish in any order, but the report always lists them in plan order. A
    parallel run and a serial run produce the same output, so diffing CI logs is
    meaningful.

---

## `fail-fast`

```toml
fail-fast = true
```

On the first failure, no **not-yet-started** hook is launched; in-flight hooks finish.
Anything that never started is reported as not-run:

```console
FAIL  ruff       (0.20s)
      src/app.py:1:1: F401 unused import
----  mypy       (not run)

0 passed, 1 failed, 1 not run
```

Good for a fast local commit hook. In CI you usually want `false` — one run that tells
you about every problem beats three round-trips.

---

## `on-event` and git hooks

```toml
[group.format]
hooks    = ["ruff-format"]
on-event = "commit"

[group.full]
hooks    = ["ruff", "mypy", "tests"]
on-event = "push"

[group.msg]
hooks    = ["conventional-commit"]
on-event = "commit-msg"
```

| `on-event` | git hook |
|---|---|
| `commit` | `.git/hooks/pre-commit` |
| `push` | `.git/hooks/pre-push` |
| `commit-msg` | `.git/hooks/commit-msg` |

Only these three values are accepted; anything else is rejected at load.
[`gatecheck install`](../cli/install.md) writes the scripts. Groups without an
`on-event` never fire automatically — run them by name.

A `commit-msg` group checks the commit message instead of the changeset. Git passes
the path of the pending message file, which gatecheck forwards to the group's hooks
via the [`{commit-msg}`](../cli/run.md#message-check-mode) placeholder — see
[`gatecheck run`](../cli/run.md#message-check-mode).

Several groups can share an event; they run in declared order, and the first failure
stops the commit.

---

## A worked layout

```toml
# Fast, auto-fixing, on every commit
[group.format]
hooks     = ["ruff", "ruff-format"]
parallel  = false          # ruff-format depends on ruff anyway
fail-fast = true
on-event  = "commit"

# Everything, in parallel, before it leaves your machine
[group.full]
hooks       = ["ruff", "ruff-format", "mypy", "cargo-clippy", "shellcheck"]
parallel    = true
max-workers = 4
fail-fast   = false
on-event    = "push"
```

Commit stays fast; push is thorough; CI runs `gatecheck run full --base main`.

## See also

- [Conditions & Filters](conditions.md) — deciding whether a hook runs at all.
- [`gatecheck run`](../cli/run.md) — the execution pipeline end to end.
- [`gatecheck install`](../cli/install.md) — wiring `on-event` to git.
