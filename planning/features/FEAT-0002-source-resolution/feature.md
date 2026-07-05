---
id: FEAT-0002
title: Source resolution
status: Draft
owner: TBD
date: 2026-06-28
prd: PRD-0001 § Scope — Sources
adrs: [ADR-0001]
---

# FEAT-0002: Source resolution

## Summary

Turn each hook's `from` source spec — `pypi:ruff>=0.4`, `pypi+internal:my-linter==1.0`, `project`, `system` — into a concrete, runnable environment for the runner. This is the bridge between the validated config model (FEAT-0001) and an actual executable: parse and classify the spec, then resolve it to a binary the runner can invoke.

## Why

`pypi:` is the source of truth for hooks (PRD-0001 § Goals 1) and reusing the project's own venv via `from = "project"` (PRD-0001 § Goals 2) are two of the headline reasons `gatecheck` exists. The config loader only validates that a `from` string is non-empty; nothing yet understands what `pypi+internal:my-linter==1.0` *means*. This feature gives that string semantics. See [PRD-0001 § Scope — Sources](../../prd/0001-gatecheck.md#scope) ("PyPI / private registries / project venv / system binary resolution") and [ADR-0001](../../adr/0001-python-host-rust-core.md), which places package resolution and environment management on the Python host side.

## User-facing surface

The contract is the `from` field documented in [docs/config/reference.md § Source spec syntax](../../../docs/config/reference.md#source-spec-syntax). FEAT-0002 gives these specs behavior:

| Spec form | Example | Meaning |
|---|---|---|
| `pypi:<spec>` | `from = "pypi:ruff>=0.4,<1"` | Public PyPI; resolve via the `[sources] default-registry`. |
| `pypi+<alias>:<spec>` | `from = "pypi+internal:org-linter==2.1.0"` | Private registry named `<alias>`, declared in `[sources]`. |
| `project` | `from = "project"` | Reuse the project's own activated venv — no new env created. |
| `system` | `from = "system"` | No env management — resolve the command against the raw `PATH`. |

`local:`, `git:`, and `docker:` specs also appear in the reference table; FEAT-0002 covers only the four forms above. The others are recognized as a typed "unsupported source kind" and produce a clear error rather than a crash; full support for them is out of scope for this feature.

Errors in a `from` spec surface through the existing `gatecheck.config.ConfigError` `path:line:col: message` mechanism where the spec originates from a loaded `check.toml`, so users get the same IDE-parseable diagnostics they already get for the rest of the config.

## Out of scope

- **Actual PyPI / private-registry network resolution and venv creation.** Talking to an index, picking a version, and building a `uv`-backed cached venv belong to the **Environments** feature (PRD-0001 § Scope — Environments). FEAT-0002 stops at producing a typed, validated description of a `pypi:` / `pypi+alias:` source plus the resolution of the *non-network* kinds (`project`, `system`).
- **The cache key / hit-miss explainability** for resolved environments (PRD-0001 § Scope — Cache).
- **`local:` / `git:` / `docker:` source kinds** beyond recognizing and rejecting them with a typed error.
- **Running the resolved executable** — that is the runner's job (PRD-0001 § Scope — Runner).
- **Workspace-aware resolution** (per-package interpreter selection) — that layers on top once the workspace feature lands.

## Stories

A vertical-slice breakdown: parse first (pure, no I/O), then resolve the two non-network kinds, then hand the network kind to Environments.

- [ ] [STY-0004 — Parse and classify a hook's source spec into a typed, validated model](stories/STY-0004-parse-classify-source-specs.md)
- [ ] [STY-0005 — Resolve `from = "project"` and `from = "system"` to concrete executables](stories/STY-0005-resolve-project-system-sources.md)
- [ ] STY-0006 — Resolve `pypi:` / `pypi+alias:` specs against a registry (network; overlaps Environments — defines the boundary) (not yet written)

## Acceptance

- Every documented `from` form (`pypi:`, `pypi+alias:`, `project`, `system`) parses into a distinct, typed in-memory source kind that downstream code can `match` on without re-parsing the raw string.
- A malformed `from` spec produces a `ConfigError` whose first line matches `check.toml:\d+:\d+:` and whose message names the offending hook and spec.
- `from = "project"` and `from = "system"` resolve to a concrete executable (or a clear "not found on PATH / not in project venv" error) without any network access or venv creation.
- `pypi:` / `pypi+alias:` resolution is delegated to the Environments feature across a documented, typed boundary — FEAT-0002 produces the validated request; it does not perform the network round-trip.
- The whole feature is importable and testable in a pure-Python environment with no dependency on the Rust core (per ADR-0001).
