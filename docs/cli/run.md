# `gatecheck run`

Execute hooks against a changeset and report the result.

```console
$ gatecheck run [OPTIONS] [GROUP]
```

With no `GROUP`, every hook in `check.toml` runs. With one, only that
[group's](../config/groups.md) hooks run, in its declared order.

## Options

| Option | Default | Description |
|---|---|---|
| `--config FILE` | discovered | Path to the config. Default: found by searching upward for `check.toml` or a `[tool.gatecheck]` `pyproject.toml`. |
| `--all-files` | off | Run against every **tracked** file instead of the staged set. |
| `--base REF` | — | Run against files changed since `REF`. Mutually exclusive with `--all-files`. |
| `--affected` | off | Monorepo: run only the hooks of [affected packages](../guides/monorepo.md). |
| `--offline` | off | Never touch the network; sets `GATECHECK_OFFLINE`. See [Air-gapped](../guides/air-gapped.md). |
| `--json` | off | Emit the report as JSON instead of the human rendering. |

## Choosing the changeset

This is the decision that matters most, and the default is the one you want locally:

=== "Staged (default)"

    ```bash
    gatecheck run
    ```

    The files in the git index — exactly what a commit would contain. This is what
    the installed git hooks use.

=== "Since a ref"

    ```bash
    gatecheck run --base main
    ```

    Everything changed relative to `REF`, using **merge-base** semantics
    (`REF...HEAD`). A branch that has fallen behind reports only its own changes,
    not everything `main` moved on by. This is the right choice in CI, where
    nothing is staged.

=== "Everything tracked"

    ```bash
    gatecheck run --all-files
    ```

    Every tracked file. Useful for a one-off sweep after adopting a new hook.

Deleted files are never included — you can't lint a file that's gone.

## Reading the output

```console
$ gatecheck run

ok    ruff             (0.31s)
FAIL  mypy             (1.44s)
      src/app.py:12: error: Missing return type annotation
skip  license-audit    (requires network — skipped in offline mode)
----  integration      (not run)

1 passed, 1 failed, 1 skipped, 1 not run
```

| Prefix | Meaning |
|---|---|
| `ok` | The hook exited `0`. |
| `FAIL` | The hook exited non-zero. Its output is shown indented beneath. |
| `ERR` | The hook could not be executed at all — environment could not be resolved, or the command could not be spawned. |
| `skip` | The hook was excluded before it ran; the reason is in parentheses. |
| `----` | The hook was planned but never started, because `fail-fast` stopped the run. |

A hook is skipped when a [`when` condition](../config/conditions.md) excludes it, or
when its `files` glob matches nothing in this changeset. Skips are **not** failures —
they don't affect the exit code.

!!! note "Why a hook with no matching files is skipped"

    With an empty file list, `run = "ruff check --fix {files}"` would become
    `ruff check --fix` — and most tools read "no paths" as "scan everything". A
    `--fix` hook would then rewrite files your change never touched. Hooks with
    `pass-files = false` are exempt: they never wanted files and are meant to run
    project-wide.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Nothing failed or errored. Skipped and not-run hooks don't count against you. |
| `1` | At least one hook failed or errored — or the config, group or git ref was invalid. |

## JSON output

`--json` prints the report as a single JSON document and nothing else, so it pipes
straight into `jq`. The exit code is unchanged, so it still works as a gate.

```console
$ gatecheck run --json | jq '.summary'
{
  "passed": 4,
  "failed": 1,
  "error": 0,
  "skipped": 1,
  "not_run": 0
}
```

```json title="Shape"
{
  "results": [
    {"hook_id": "ruff", "status": "passed", "exit_code": 0,
     "duration": 0.31, "output": ""}
  ],
  "skipped": [{"hook_id": "net", "reason": "requires network — skipped in offline mode"}],
  "not_run": ["integration"],
  "summary": {"passed": 1, "failed": 0, "error": 0, "skipped": 1, "not_run": 1},
  "exit_code": 0
}
```

Under `--affected`, each `hook_id` carries a `<package>:<hook>` prefix.

## How a run is built

1. **Resolve the changeset** — staged, `--base REF`, or `--all-files`, via git.
2. **Plan** — select the group (or all hooks), drop those excluded by `when` or by an
   empty file set, and topologically sort the rest by `depends-on` into levels.
3. **Route files** — each hook gets the changeset filtered by its `files` and
   `exclude` globs (or nothing, when `pass-files = false`).
4. **Execute** — the Rust core schedules hooks dynamically: each starts the moment
   its dependencies finish, bounded by the group's `max-workers`.
5. **Report** — render, and exit `0` or `1`.

See [check.toml Reference](../config/reference.md) for the full pipeline, and
[Groups & Ordering](../config/groups.md) for `depends-on`, `parallel`, `fail-fast`
and `max-workers`.

## Examples

```bash
# Before committing — check what's staged
gatecheck run

# Just the lint group
gatecheck run lint

# CI on a pull request
gatecheck run --base "$GITHUB_BASE_REF"

# Monorepo CI — only packages the PR touches, and their dependents
gatecheck run --affected --base main

# Sandboxed runner with a warm cache
gatecheck run --offline --base main

# Feed results to another tool
gatecheck run --json | jq -r '.results[] | select(.status=="failed") | .hook_id'
```
