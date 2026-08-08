---
hide:
  - toc
---

# hooksmith documentation

Technical reference for [**hooksmith**](https://hooksmith.dev) — the next-generation runner for your git pre-commit actions, with real package sources, monorepo support, and a Rust-powered parallel runner.

!!! tip "New here?"
    The [Quick Start](getting-started/quickstart.md) gets you a working install and your first hook running in two minutes.

## Start here

<div class="grid cards" markdown>

-   **[Quick Start](getting-started/quickstart.md)**

    Install hooksmith, write your first `check.toml`, and run a hook.

-   **[Importing your existing hooks](getting-started/migration.md)**

    `hooksmith migrate` reads your existing hook config and writes a working `check.toml`.

-   **[Installation](getting-started/installation.md)**

    PyPI, uv, pipx, and prebuilt wheel notes.

</div>

## Reference

<div class="grid cards" markdown>

-   **[Config Reference](config/reference.md)**

    Every key in `check.toml` — hooks, sources, groups, conditions, workspace.

-   **[CLI Reference](cli/index.md)**

    `install`, `sync`, `run`, `cache`, `migrate` — every flag and subcommand.

-   **[Sources](config/sources.md)**

    PyPI, private registries, project venv, system binaries, git refs.

-   **[Groups & conditions](config/groups.md)**

    Compose hooks into named groups; gate them on branches, env vars, or CI.

</div>

## Guides

<div class="grid cards" markdown>

-   **[Monorepos](guides/monorepo.md)**

    Per-package configs, dependency graphs, `--affected` execution.

-   **[Private registries](guides/private-registries.md)**

    Auth, mirrors, and lockfile reproducibility.

-   **[CI integration](guides/ci.md)**

    GitHub Actions, GitLab CI, and what to cache.

-   **[Custom hooks](guides/custom-hooks.md)**

    Publishing a hook to PyPI so others can `from = "pypi:your-hook"`.

</div>

## Design

The [design docs](design/index.md) explain how hooksmith is put together — useful when you want to extend it, debug a surprising behavior, or understand a tradeoff.

- [Architecture overview](design/architecture.md) — the Python host / Rust core split, data flow per command.
- [Design rationale](design/why-not-precommit.md) — the constraints that drove hooksmith to exist.
- [Versioning](design/versioning.md) — how the CI computes versions from conventional commits.
- [Rust core internals](design/rust-core.md) — the DAG solver, runner, and cache.

## Looking for the marketing page?

The landing page lives at the root of [**hooksmith.dev**](https://hooksmith.dev). This site is the technical reference behind it.
