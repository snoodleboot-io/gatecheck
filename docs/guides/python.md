# Python Projects

A realistic `check.toml` for a Python project, and the reasoning behind each choice.

## The config

```toml title="check.toml"
[[hook]]
id      = "ruff"
from    = "pypi:ruff==0.4.9"
run     = "ruff check --fix {files}"
files   = "*.py"
exclude = "migrations/*"

[[hook]]
id         = "ruff-format"
from       = "pypi:ruff==0.4.9"
run        = "ruff format {files}"
files      = "*.py"
exclude    = "migrations/*"
depends-on = ["ruff"]

[[hook]]
id         = "mypy"
from       = "project"
run        = "mypy src/"
pass-files = false
when       = { files-match = "*.py" }

[group.commit]
hooks     = ["ruff", "ruff-format"]
fail-fast = true
on-event  = "commit"

[group.full]
hooks       = ["ruff", "ruff-format", "mypy"]
parallel    = true
max-workers = 4
on-event    = "push"
```

```bash
hooksmith sync      # build the environments once
hooksmith install   # wire up pre-commit and pre-push
```

## Why it's shaped like that

**ruff comes from `pypi:`, mypy from `project`.**

This is the one decision that matters. `ruff` is self-contained — it reads your files
and needs nothing else — so hooksmith installs a pinned copy in an isolated venv.
Everyone on the team and CI gets byte-identical behaviour, with no "works on my
machine".

`mypy` is different: it must **import your dependencies** to type-check against them.
A mypy in an isolated venv would see none of your packages and report nonsense. So it
runs from your project venv, where your dev dependencies already live.

The rule generalizes: **isolate tools that only read your source; use `project` for
tools that need to resolve your imports.**

**The version is pinned exactly.** `==0.4.9`, not `>=0.4`. A formatter that changes
behaviour on a Tuesday because upstream released is a bad day for everyone. Exact pins
also keep the cache key stable and are required for [offline runs](air-gapped.md).

**Both ruff hooks share one environment.** Same package, same version, same index —
one venv, built once, used by both. That's the content-addressed cache doing its job.

**`ruff-format` depends on `ruff`.** Lint fixes first, then formatting, so the
formatter has the last word on layout. Without the dependency they could run
simultaneously and fight over the same file.

**mypy has `pass-files = false` and a `files-match` condition.** It always checks all
of `src/` (partial type-checking gives misleading results), but only when the change
actually contains Python. Those two settings together are the idiom for "project-wide
tool, conditionally relevant".

**Two groups.** Commit is fast and auto-fixing with `fail-fast = true`; push runs
everything in parallel. You get quick feedback while working and a thorough check
before anything leaves your machine.

## Adding more tools

```toml
[[hook]]
id         = "bandit"
from       = "pypi:bandit==1.7.9"
run        = "bandit -q -c pyproject.toml {files}"
files      = "*.py"
exclude    = "tests/*"

[[hook]]
id    = "codespell"
from  = "pypi:codespell==2.3.0"
run   = "codespell {files}"

[[hook]]
id         = "pytest"
from       = "project"
run        = "pytest -q"
pass-files = false
when       = { on-ci = true }
```

`pytest` is `project` for the same reason as mypy — it imports your code — and
`on-ci = true` keeps a slow suite out of your commit loop while still gating CI.

## Escape hatches

```toml
when = { env-not = "SKIP_MYPY" }
```

```bash
SKIP_MYPY=1 git commit -m "wip"    # skip one hook, deliberately
git commit --no-verify             # skip everything (git's own flag)
```

Prefer the first: it's explicit, reviewable, and shows up in the report as a skip with
a reason.

## Src layout and imports

`from = "project"` looks in `$VIRTUAL_ENV` first, then `<root>/.venv`. If your team
uses a different venv location, activate it before running hooksmith, or install the
tool from `pypi:` instead where that's viable.

For a `src/` layout, make sure the package is installed (`pip install -e .`) so mypy
and pytest can import it — that's a project-setup concern, not a hooksmith one, but
it's the usual cause of "works in my editor, fails in the hook".

## See also

- [Source Types](../config/sources.md) — the `pypi:` / `project` / `system` decision in full.
- [CI Integration](ci.md) — making this a gate.
- [Monorepo Setup](monorepo.md) — several Python packages in one repo.
