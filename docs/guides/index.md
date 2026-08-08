# Guides

Task-shaped walkthroughs. For field-by-field detail, see
[Configuration](../config/index.md); for command detail, the
[CLI Reference](../cli/index.md).

<div class="grid cards" markdown>

-   **[Python Projects](python.md)**

    The common setup: ruff, mypy, and where `pypi:` vs `project` belongs.

-   **[Monorepo Setup](monorepo.md)**

    Workspaces, the package dependency graph, and `--affected`.

-   **[CI Integration](ci.md)**

    Running in GitHub Actions, caching environments, `--base` in a PR job.

-   **[Air-gapped / Offline](air-gapped.md)**

    Sync online, run offline. Cache restore and internal indexes.

-   **[Private Registries](private-registries.md)**

    Internal indexes, aliases, and authentication.

-   **[Writing Custom Hooks](custom-hooks.md)**

    Project scripts, non-Python tools, and hooks that aren't published anywhere.

</div>

## If you're just starting

1. [Quick Start](../getting-started/quickstart.md) — the shortest path to a working setup.
2. [Python Projects](python.md) — a realistic config to copy.
3. [CI Integration](ci.md) — make it a gate, not just a local convenience.

Already on pre-commit? [`hooksmith migrate`](../cli/migrate.md) converts your config,
and [Why not pre-commit](../design/why-not-precommit.md) covers what changes.
