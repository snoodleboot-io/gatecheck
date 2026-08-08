---
id: FEAT-0003
title: Environments
status: Draft
owner: TBD
date: 2026-07-05
prd: PRD-0001 § Scope — Environments (+ Cache)
adrs: [ADR-0001]
---

# FEAT-0003: Environments

## Summary

Turn a resolved hook source into an **executable environment** the runner can
invoke. This is the last hop before execution: given a `HookDef`, produce a
`ResolvedEnv(bin_dir, cache_key)` — a directory that contains the hook's command
plus a deterministic key identifying that environment for caching. For
`from = "project"` / `from = "system"` this reuses an already-installed
interpreter or binary (no new environment); for `pypi:` / `pypi+alias:` it
creates (or reuses from cache) a **uv-backed** virtualenv with the pinned
distribution installed, isolated per pinned dist.

## Why

Two of `hooksmith`'s headline goals live here: **"Reuse the project's own venv"**
for tools that already exist (PRD-0001 § Goals 2) and **uv-backed, cached,
isolated environments** for `pypi:` hooks so the same tool is never built twice
(PRD-0001 § Goals 1, § Success metrics — cached `run` under 250 ms). FEAT-0002
stops at a *description* of a source: `resolve_source` locates the local kinds and
`registry.resolve_pypi_source` pins a `pypi:` requirement to
`name==version --index-url <url>`, but nothing yet turns either into a directory
of runnable executables. This feature is that bridge. See
[PRD-0001 § Scope — Environments](../../prd/0001-hooksmith.md#scope) ("uv-backed
venv creation, caching, isolation") and § Cache ("SHA-256 keying, hit/miss
explainability"), and [ADR-0001](../../adr/0001-python-host-rust-core.md), which
places package resolution and environment management on the Python host side.

## User-facing surface

The runner-facing contract is a single entry point on `EnvManager`:

```python
from hooksmith.env import EnvManager, ResolvedEnv

env: ResolvedEnv = EnvManager(workspace_root=root, environ=os.environ).resolve(hook)
# env.bin_dir  -> Path to the directory containing the hook's executable
# env.cache_key -> deterministic str identifying this environment
```

`EnvManager.resolve(hook)` dispatches on the hook's `from` spec (classified by
`hooksmith.sources.parse_source`) and the tool named by `hook.run`:

| `from` spec | Handling | Environment produced |
|---|---|---|
| `project` | `resolve_source` → existing project venv binary | `bin_dir` = the resolved executable's parent; **no env created** |
| `system` | `resolve_source` → binary on `PATH` | `bin_dir` = the resolved executable's parent; **no env created** |
| `pypi:<spec>` / `pypi+<alias>:<spec>` | `registry.resolve_pypi_source` → pinned dist, then **`uv`** builds/reuses a cached venv | `bin_dir` = the cached venv's `bin/`; content-addressed, isolated per pinned dist |
| `local:` / `git:` / `docker:` (unsupported) | rejected with a typed error (same as `resolve_source`) | — |

`ResolvedEnv` is the existing frozen dataclass
(`src/hooksmith/env/manager.py`): `bin_dir: Path`, `cache_key: str`.

## uv is an external runtime dependency (flag)

The `pypi:` path **shells out to the `uv` binary as a subprocess** (`uv venv`,
`uv pip install …`). This is an **external tool/runtime dependency**, *not* a
Python package added to `pyproject.toml` — it is a program that must be present on
the host, discovered at run time. This distinction (external binary vs. declared
package dependency) is called out here per core conventions and must be approved at
the architect/design gate for the `pypi` slice (STY-0008); the non-venv slice
(STY-0007) invokes no subprocess at all. Caching, isolation, and the exact
cache-key inputs for uv-backed venvs are sketched below but the deep design is left
to the architect.

## Out of scope

- **Running the resolved executable.** Assembling argv, passing changed files,
  streaming output, exit-code handling — that is the runner (PRD-0001 § Scope —
  Runner).
- **Network resolution / version pinning of `pypi:` specs.** That is FEAT-0002's
  `registry.resolve_pypi_source` (STY-0006); this feature *consumes* its
  `ResolvedPyPISource`.
- **Parsing / classifying the `from` spec.** Done by `sources.parse_source`
  (STY-0004); this feature consumes `ParsedSource`.
- **`local:` / `git:` / `docker:` source kinds** beyond recognizing and rejecting
  them with a typed error (they never build an environment in v1).
- **Workspace-aware / per-package interpreter selection.** Layers on once the
  workspace feature lands; `EnvManager` takes a single `workspace_root` for now.
- **Cache eviction / GC policy.** Building content-addressed cache directories is
  in scope (STY-0008); pruning them is a later concern.

## Stories

A vertical-slice breakdown: establish the `EnvManager` contract and the pure,
no-I/O non-venv path first; then the uv-backed venv build (subprocess + network +
filesystem); then cache explainability.

- [ ] [STY-0007 — `EnvManager` skeleton + the non-venv path (`project` / `system` → `ResolvedEnv`); `pypi` deferred](stories/STY-0007-env-manager-non-venv-path.md)
- [ ] STY-0008 — uv-backed venv creation for `pypi:` / `pypi+alias:` sources: shell out to `uv venv` + `uv pip install name==version --index-url <url>` (with `--require-hashes` when `sha256` present) into a content-addressed cache dir; return its `bin/` (subprocess + filesystem + network) (not yet written)
- [ ] STY-0009 — Cache management + explainability: SHA-256 keying, hit/miss trace, `hooksmith cache why <hook>` (PRD-0001 § Scope — Cache) (not yet written)

## Acceptance

- `EnvManager.resolve(hook)` returns a `ResolvedEnv(bin_dir, cache_key)` for every
  supported `from` kind; `bin_dir` is a directory that contains the executable named
  by `hook.run`.
- `from = "project"` and `from = "system"` reuse an existing binary via
  `resolve_source` and create **no** new environment, **no** subprocess, and touch
  **no** network.
- `pypi:` / `pypi+alias:` build (or reuse from cache) a uv-backed venv isolated per
  pinned distribution, keyed by a deterministic `cache_key`; the same pinned dist
  never builds twice.
- `cache_key` is a deterministic function of the environment's identifying inputs
  (resolved executable for the non-venv kinds; pinned `name`+`version`+`index_url`
  for the `pypi` kinds), stable across processes.
- Resolution failures surface as typed errors (reusing `SourceResolutionError` /
  `RegistryError` from FEAT-0002 where applicable, plus a feature-local `EnvError`
  for env-build failures), never raw exceptions.
- The non-venv path (STY-0007) is importable and fully unit-testable in a pure
  Python environment with no subprocess, network, or Rust-core dependency (per
  ADR-0001).
