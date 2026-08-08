# Getting Started

hooksmith runs your linters, formatters and checks against the files you're about to
commit — like pre-commit, but with real package sources, a dependency-aware parallel
scheduler, and a cache you can interrogate.

## Where to start

<div class="grid cards" markdown>

-   **[Installation](installation.md)**

    Requirements, building from source, and how `uv` is handled.

-   **[Quick Start](quickstart.md)**

    A working `check.toml`, hooks wired to git, in a couple of minutes.

-   **[Migration from pre-commit](migration.md)**

    Convert an existing `.pre-commit-config.yaml` and check the result before
    switching.

</div>

## The shape of it

Configuration is one TOML file:

```toml title="check.toml"
[[hook]]
id    = "ruff"
from  = "pypi:ruff==0.4.9"
run   = "ruff check --fix {files}"
files = "*.py"

[group.lint]
hooks    = ["ruff"]
on-event = "commit"
```

Three concepts, and that's most of it:

**Hooks** are things to run. `from` says where the tool comes from — a pinned package
(`pypi:ruff==0.4.9`), your project's venv (`project`), or whatever is on `PATH`
(`system`). See [Source Types](../config/sources.md).

**Groups** collect hooks and decide how they execute — in parallel or serially, with
or without fail-fast — and which git event they fire on. See
[Groups & Ordering](../config/groups.md).

**Conditions** decide whether a hook runs at all for this change: which branch you're
on, which files changed, whether you're in CI. See
[Conditions & Filters](../config/conditions.md).

## What happens on a run

```bash
hooksmith run
```

1. Ask git what changed (staged by default; `--base main` in CI).
2. Work out which hooks apply, and skip the rest **with a reason** — never silently.
3. Resolve each hook's environment, reusing the content-addressed cache.
4. Execute, starting each hook the moment its dependencies finish.
5. Print a report and exit `0` or `1`.

Nothing about that is magic, and every step is inspectable —
[`hooksmith cache why <hook>`](../cli/cache.md) will show you exactly why an
environment was reused or rebuilt.

## Coming from pre-commit?

[Why not pre-commit](../design/why-not-precommit.md) explains what's different and
why. If you just want to move, [`hooksmith migrate`](../cli/migrate.md) converts your
config and tells you about anything it wasn't sure of.
