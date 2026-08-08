---
id: PRD-0001
title: hooksmith — a modern pre-commit replacement
status: Draft
author: TBD
date: 2026-05-28
---

# PRD-0001: hooksmith

## Problem

`pre-commit` has been the default Python project's git-hook runner for nearly a decade. The world around it has changed and the tool hasn't:

- Hooks are distributed via GitHub URLs instead of PyPI, so private registries are awkward, version pinning is by SHA, and there's no real package metadata.
- Each hook gets its own shadow venv, even when the project already has a venv with the same tool installed.
- Monorepos are second-class — `pre-commit` has no concept of "the affected package", so every change runs every hook.
- The Python interpreter cold-start dominates wall time on small commits (~300 ms before any user code runs).
- When a cached hook fires unexpectedly (or fails to), there's no built-in way to ask *why*.

Teams either work around these gaps with bespoke scripts or accept the friction.

## Target users

- Python and polyglot teams running pre-commit hooks today, especially those with **monorepos** or **private package registries**.
- Tool authors who publish lint/format tools to PyPI and want them used directly instead of via a wrapper repo.
- Platform engineers tuning CI hot paths where a few hundred ms per commit matters.

## Goals

1. **PyPI is the source of truth.** Hooks resolve by package spec (`pypi:ruff>=0.4`, `pypi+internal:my-linter==1.0`), not GitHub URLs.
2. **Reuse the project's own venv** for tools that already live there (`from = "project"`).
3. **Monorepo-native execution.** Per-package configs, a dependency graph, and `--affected` to run only what changed.
4. **Sub-10ms startup.** Compiled Rust binary, no interpreter warmup on the hot path.
5. **Explainable caching.** `hooksmith cache why <hook>` produces a human-readable trace of the cache decision.
6. **Drop-in migration.** `hooksmith migrate` reads `.pre-commit-config.yaml` and writes a working `check.toml`.

## Non-goals

- We are not building a new linter, formatter, or test runner. hooksmith only *runs* hooks.
- We are not supporting non-git VCS in v1.
- We are not shipping a web UI or hosted service.
- We are not supporting hook discovery from arbitrary HTTP URLs — package registries only.

## Success metrics

- **Adoption**: 1,000 unique PyPI installs/week within 6 months of 1.0.
- **Performance**: p50 cold start under 10 ms; p50 cached `hooksmith run` on a 10-file commit under 250 ms.
- **Migration friction**: ≥ 90% of `hooksmith migrate` outputs run unmodified against the source repo's hook suite.
- **Support load**: median GitHub issue resolution under 7 days.

## Scope

| Area | Summary |
|---|---|
| Config | TOML schema, parsing, validation, merging across workspace packages |
| Sources | PyPI / private registries / project venv / system binary resolution |
| Environments | uv-backed venv creation, caching, isolation |
| Runner | DAG-based parallel subprocess execution (Rust + rayon) |
| Workspace | Monorepo discovery, package graph, `--affected` calculation |
| Cache | SHA-256 keying, hit/miss explainability |
| CLI | `install`, `sync`, `run`, `cache`, `migrate` (click) |
| Migration | `.pre-commit-config.yaml` → `check.toml` with known-hook mapping |

Each area becomes one or more `FEAT-NNNN` directories.

## Open questions

- Should `hooksmith` support Windows on day one, or as a fast follower? (Affects path handling in the Rust runner.)
- Is there a story for hook *authoring* (a `hooksmith-hooks` SDK), or do we treat any PyPI package as a hook host?
- How do we handle hooks that need network access in sandboxed CI environments?
