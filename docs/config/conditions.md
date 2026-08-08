# Conditions & Filters

Two independent mechanisms decide what a hook does with a given change:

- **File filters** (`files`, `exclude`) — *which files* a hook receives.
- **`when` conditions** — *whether the hook runs at all*.

A hook excluded by either is reported as **skipped, with a reason**. Skips are never
silent, and never affect the exit code.

---

## File filters

```toml
[[hook]]
id      = "ruff"
from    = "pypi:ruff==0.4.9"
run     = "ruff check --fix {files}"
files   = "*.py"
exclude = "vendor/*"
```

| Field | Effect |
|---|---|
| `files` | Only files matching this glob are passed. Unset = the whole changeset. |
| `exclude` | Files matching this glob are removed, applied *after* `files`. |
| `pass-files` | `false` = the hook receives no files at all. |

Globs are `fnmatch`-style and **case-sensitive**. `/` is matched like any other
character, so `*.py` matches at any depth — `src/deep/mod.py` included. Anchor with a
prefix when you mean it: `src/*.py`.

### Where the files go

`{files}` is substituted in place; without it, the files are appended:

```toml
run = "ruff check --fix {files} --quiet"   # ruff check --fix a.py b.py --quiet
run = "ruff check"                         # ruff check a.py b.py
```

### A hook with no matching files is skipped

```console
skip  ruff  (no matching files)
```

This is a safety rule, not an optimization. With an empty file list,
`ruff check --fix {files}` would become `ruff check --fix` — and most tools read "no
paths" as "scan everything". A `--fix` hook would then rewrite files your change never
touched.

Hooks with `pass-files = false` are exempt: they never wanted files and are meant to
run project-wide. **`pass-files = false` is therefore the "always run" escape hatch** —
there is no separate `always-run` flag.

---

## `when` conditions

```toml
when = { env-not = "SKIP_MYPY", branch-not = "release/*" }
```

All present conditions are **AND-ed** — the hook runs only if every one passes.

| Key | Type | Runs the hook when… |
|---|---|---|
| `requires-network` | bool | `true`: **skips** when the run is offline |
| `env` | string | this env var is set |
| `env-not` | string | this env var is **not** set |
| `on-ci` | bool | `true`: only in CI · `false`: never in CI |
| `branch` | string | the current branch is exactly this |
| `branch-not` | glob | the branch does **not** match |
| `branch-matches` | glob | the branch matches |
| `files-match` | glob | at least one changed file matches |

Conditions are checked in the order above, and the **first one that fails is the
reported reason** — so an explicit condition always wins over the generic
"no matching files".

### Environment

```toml
when = { env-not = "SKIP_MYPY" }   # an escape hatch: SKIP_MYPY=1 git commit
when = { env = "DEPLOY" }          # only when DEPLOY is set
```

Any non-empty value counts as set.

### CI

```toml
when = { on-ci = true }    # heavy checks: CI only
when = { on-ci = false }   # auto-fixers: local only
```

CI is detected via `CI` or `GITHUB_ACTIONS`.

### Branch

```toml
when = { branch = "main" }             # exact match only
when = { branch-not = "release/*" }    # glob — skip on release branches
when = { branch-matches = "feat/*" }   # glob — only on feature branches
```

`branch` is an exact string; `branch-not` and `branch-matches` are globs. The branch
comes from `git branch --show-current`, which is **empty on a detached HEAD** — in
that state the branch conditions don't apply and the hook runs.

### Changed files

```toml
when = { files-match = "*.py" }
```

Runs only if the changeset contains at least one match. Note the difference from
`files`: `files-match` gates *the whole hook*, while `files` selects *which files it
receives*. Use `files-match` for a project-wide hook that's only relevant when certain
files changed:

```toml
[[hook]]
id         = "mypy"
from       = "project"
run        = "mypy src/"      # always checks all of src/
pass-files = false
when       = { files-match = "*.py" }   # …but only when Python changed
```

### Network

```toml
when = { requires-network = true }
```

For hooks that reach the network *at run time* — a license API, a linter that phones
home. In an [offline run](../guides/air-gapped.md) they're skipped rather than left to
fail confusingly:

```console
skip  license-audit  (requires network — skipped in offline mode)
```

Online it's a no-op. Checked first, so it's the reason you see when it applies.

---

## When context is missing, conditions fail open

The branch and `files-match` conditions need git context. Where that isn't available,
the condition is **skipped and the hook runs** — hooksmith won't skip your checks
because it couldn't determine something.

---

## Worked example

```toml
[[hook]]
id         = "mypy"
from       = "project"
run        = "mypy src/"
pass-files = false
when       = { env-not = "SKIP_MYPY", on-ci = false, branch-not = "release/*" }
```

Runs when: `SKIP_MYPY` is unset **and** this isn't CI **and** the branch isn't
`release/*`.

```console
$ SKIP_MYPY=1 hooksmith run
skip  mypy  (env SKIP_MYPY is set)

$ git switch release/2.0 && hooksmith run
skip  mypy  (branch 'release/2.0' matches branch-not 'release/*')
```

## See also

- [check.toml Reference](reference.md) — the field tables.
- [Groups & Ordering](groups.md) — `depends-on` and what happens when a dependency is skipped.
