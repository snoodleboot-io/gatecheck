---
id: BUILD-0007-CHARTER
title: Build charter for STY-0007 (EnvManager skeleton + non-venv path; pypi deferred)
parent: BUILD-0007
target_story: STY-0007
status: Locked
date: 2026-07-05
---

# BUILD-0007 Charter — STY-0007 (`EnvManager` skeleton + the non-venv path; `pypi` deferred)

## Goal

Build out the existing `EnvManager` stub so `EnvManager.resolve(hook) ->
ResolvedEnv` turns a `HookDef` whose `from` is `project` or `system` into a
`ResolvedEnv(bin_dir, cache_key)` — the runner-facing contract for getting an
executable environment for a hook. Classify the spec with
`gatecheck.sources.parse_source`, derive the tool name from `hook.run`, locate the
executable with `gatecheck.sources.resolve_source`, and derive a **deterministic
`cache_key`**. This is the **non-venv path only**: `pypi:` / `pypi+alias:` and the
unsupported kinds route to a typed, deferred `EnvError`.

This is the first vertical slice of FEAT-0003 (Environments): establish the
contract, the `ResolvedEnv` value, and the `cache_key` scheme that STY-0008
(uv-backed venvs) and STY-0009 (cache explainability) build on — **pure and
hermetic**, with **NO subprocess, NO network, NO filesystem writes, NO venv
creation**. See
[STY-0007](../features/FEAT-0003-environments/stories/STY-0007-env-manager-non-venv-path.md),
[FEAT-0003](../features/FEAT-0003-environments/feature.md),
[PRD-0001 § Scope — Environments](../prd/0001-gatecheck.md#scope), and
[ADR-0001](../adr/0001-python-host-rust-core.md).

## Design-gate decisions (GRANTED — build to these)

1. **Tool name is derived as `shlex.split(hook.run)[0]`.** No `HookDef.tool`
   schema change; no new config field. POSIX `shlex` (not `str.split`) so quoted /
   escaped program names tokenize the way the runner will.
2. **STY-0007 is the non-venv path only.** `project` / `system` → `ResolvedEnv`
   via `resolve_source`; `pypi` / `pypi+alias:` → deferred `EnvError` (STY-0008);
   `local:` / `git:` / `docker:` (`UnsupportedSource`) → unsupported `EnvError`.
   **No subprocess, no network, no venv creation, no filesystem writes.**
3. **No new runtime dependency.** `shlex` / `hashlib` / `pathlib` /
   `collections.abc` are stdlib; `uv` and `packaging` are not involved in this
   slice.
4. **`ResolvedEnv` stays a frozen dataclass** (as the existing stub defines it) —
   a tracked interface kept byte-for-byte stable for STY-0008 / STY-0009 / the
   runner. See architecture-decision §3.
5. **`EnvManager` does not wrap `SourceResolutionError` / `SourceSpecError`.** They
   propagate unchanged, preserving their structured fields. `EnvError` is
   introduced only for env-management-domain failures.

## In-scope for this build

Single-PR vertical slice. New + built-out code lands in the existing leaf package
`src/gatecheck/env/` (one class / function-group per file, per core conventions):

- `src/gatecheck/env/env_error.py` — **NEW.** `EnvError(ValueError)` with
  structured `hook_id` / `reason` and the message `cannot resolve environment for
  hook '<id>': <reason>` (mirrors `SourceResolutionError`'s shape).
- `src/gatecheck/env/manager.py` — **EDIT (build out).** Add
  `EnvManager.__init__(self, workspace_root: Path | None = None, environ:
  Mapping[str, str] | None = None)` (both stored, forwarded to `resolve_source`);
  implement `resolve(hook) -> ResolvedEnv` (`parse_source` → tool-name derivation →
  `match` dispatch); add the private `_derive_tool` + `_cache_key` helpers and
  `_CACHE_KEY_SCHEME = "env-v1"`. The `ResolvedEnv` frozen dataclass **stays here**,
  unchanged.
- `src/gatecheck/env/__init__.py` — **EDIT.** Export `EnvError` alongside
  `EnvManager` / `ResolvedEnv`; set `__all__` (alphabetical, uppercase-first).
- Unit tests `tests/unit/test_env_manager.py` (hermetic; inject `workspace_root` +
  `environ`; `tmp_path` fake `.venv/bin` + fake `PATH` dir; no subprocess, no
  network).
- Acceptance tests `tests/integration/test_env_resolution_acceptance.py` (3–5
  hermetic tests; a `subprocess` spy asserts nothing is spawned).
- An "Environments — resolving a hook to an executable" subsection added to
  `docs/config/reference.md`.

## Out of scope (deferred)

- **uv-backed venv creation for `pypi:` / `pypi+alias:`** — shelling out to `uv
  venv` / `uv pip install`, content-addressed cache dirs, `--require-hashes` —
  **STY-0008.** This story only *routes* `pypi` to a deferred `EnvError`; that
  branch is the single, clearly-marked seam STY-0008 replaces.
- **Calling `registry.resolve_pypi_source`** — consumed in STY-0008, not here.
- **Cache hit/miss tracing and `gatecheck cache why`** — **STY-0009.** This story
  defines the `cache_key` *derivation* but stores / explains nothing.
- **Running the executable** (argv assembly, changed-file passing, output
  streaming, exit codes) — the runner.
- **Workspace-aware / per-package interpreter selection** — a single
  `workspace_root` is enough now.
- **`cache_root` / uv-path / client constructor parameters** — belong to
  STY-0008 / STY-0009; not added now.

## Success criteria

Verbatim from
[STY-0007](../features/FEAT-0003-environments/stories/STY-0007-env-manager-non-venv-path.md)
Acceptance criteria (AC-1 … AC-16). Highlights:

- [ ] AC-1: `EnvManager().resolve(hook)` for a `from = "system"` hook whose `run`
  names a tool on `PATH` returns `ResolvedEnv(bin_dir=<tool's parent dir>,
  cache_key=<hex>)`; `bin_dir` contains that executable.
- [ ] AC-2: `EnvManager(workspace_root=root).resolve(hook)` for `from = "project"`
  resolves from `<root>/.venv/bin` (and `$VIRTUAL_ENV/bin` when `environ` supplies
  it); `bin_dir` = the executable's parent.
- [ ] AC-3: The tool name is the first `shlex.split(hook.run)` token; extra argv
  tokens are ignored for resolution.
- [ ] AC-4: `cache_key` is a 64-char lowercase hex SHA-256 digest over
  `"env-v1\n<origin>\n<absolute executable path>"`.
- [ ] AC-5: `cache_key` is deterministic — two calls with the same hook,
  `workspace_root`, `environ`, and filesystem state return equal `cache_key` and
  equal `ResolvedEnv`.
- [ ] AC-6: The same executable reached via `project` vs `system` produces
  **different** `cache_key`s (`origin` is part of the material).
- [ ] AC-7: `pypi:` / `pypi+alias:` each raise `EnvError` naming the hook id and
  stating the `pypi` path is deferred to STY-0008 — **no** `resolve_source` call,
  **no** subprocess, **no** network.
- [ ] AC-8: `local:` / `git:` / `docker:` (`UnsupportedSource`) raise `EnvError`
  (unsupported kind).
- [ ] AC-9: A `run` that yields no tokens (whitespace-only) or has unbalanced
  quotes raises `EnvError` naming the hook and the `run` string.
- [ ] AC-10: A `project`/`system` tool that cannot be located propagates
  `SourceResolutionError` **unchanged** — `EnvManager` does not wrap it.
- [ ] AC-11: A malformed `from` spec propagates `SourceSpecError` unchanged.
- [ ] AC-12: `EnvError` subclasses `ValueError`, carries `hook_id` / `reason`, has
  the message form `cannot resolve environment for hook '<id>': <reason>`; never
  surfaced as `ConfigError`, carries no `line:col`.
- [ ] AC-13: The whole story runs with **no subprocess and no network**; suites are
  hermetic; `resolve` is a deterministic function of its injected inputs.
- [ ] AC-14: `from gatecheck.env import EnvManager, ResolvedEnv, EnvError` works.
- [ ] AC-15: `mypy --strict src/gatecheck/env/` passes; the `match` over
  `ParsedSource` is exhaustive.
- [ ] AC-16: `resolve` never creates, writes, or mutates any directory; `bin_dir`
  is always an already-existing directory for the resolved kinds.

## Stakeholder dependencies

- **[STY-0004](../features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md)**
  — merged; provides `parse_source(spec) -> ParsedSource` and the `ProjectSource`
  / `SystemSource` / `PyPISource` / `UnsupportedSource` union members + the
  `SourceSpecError` that `parse_source` may raise. Integration surface; not
  reshaped.
- **[STY-0005](../features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md)**
  — merged; provides `resolve_source(source, tool, *, workspace_root=None,
  environ=None) -> ResolvedTool` (`tool` / `executable: Path` / `origin`) and
  `SourceResolutionError`. `EnvManager` calls it for `project` / `system` and
  forwards `workspace_root` / `environ`. **`resolve_source` is not modified.**
- **`gatecheck.config.HookDef`** — supplies `hook.id`, `hook.from_`, `hook.run`
  (all validated non-empty by the loader). Consumed unchanged.
- **`ResolvedEnv` (existing stub)** — `bin_dir: Path`, `cache_key: str`, frozen
  dataclass. Kept byte-for-byte; only `EnvManager` around it is built out.
- **No new runtime dependency** — stdlib only. `uv` (STY-0008) is not involved.
- **Environments downstream (STY-0008 / STY-0009, the runner)** — consumers of
  `ResolvedEnv` / the `pypi` seam; out of scope here.
- **Locked architecture:**
  [0007-architecture-decision.md](0007-architecture-decision.md) — the
  code / test / review lanes consume it; any change re-opens BUILD-0007 §1.

## Deviations from the story

**None material.** The story's recorded "architect to lock" open questions are all
resolved in favour of the story's own recommendations:

1. **Tool-name derivation** — locked to `shlex.split(hook.run)[0]` (not
   `str.split`, no new `hook.tool` field), as the design gate decided.
2. **`cache_key` inputs** — locked to the full 64-char SHA-256 over
   `"env-v1\n<origin>\n<absolute executable path>"` (scheme tag + `origin` +
   resolved path; no truncation).
3. **Error strategy** — locked to *propagate* `SourceResolutionError` /
   `SourceSpecError` unwrapped and introduce `EnvError` only for the env-domain
   cases (unresolvable tool name, deferred `pypi`, unsupported kind), rather than
   wrapping every failure in a single `EnvError` domain.
4. **`ResolvedEnv` shape** — locked to the existing **frozen dataclass** (rather
   than aligning to the `sources` / `registry` frozen-pydantic idiom), preserving
   the tracked contract; rationale in architecture-decision §3.

All are the story's own recommendations; flagged here only because the story left
them explicitly open for the architect.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | `match` over `ParsedSource` is treated as non-exhaustive by `mypy --strict` (AC-15). | Low | Med — build gate friction. | The union has exactly four members; all four arms are present and each returns or raises. Mirrors `resolve_source`'s own exhaustive `match` (already passes `--strict`). No catch-all needed; adding one would mask a future 5th kind. |
| R2 | `ResolvedEnv` gets "upgraded" to pydantic, breaking the stub contract STY-0008 / STY-0009 / the runner build on (story Notes). | Low | High — silent contract drift. | Locked: keep the frozen dataclass verbatim; it holds only stdlib types (`Path` / `str`) so pydantic buys nothing. Flagged as a tracked interface in architecture-decision §3. |
| R3 | `SourceResolutionError` / `SourceSpecError` get wrapped in `EnvError`, hiding `tool` / `kind` / `reason` (AC-10/AC-11). | Low | Med — lossy diagnostics. | Locked decision: propagate unwrapped; `EnvError` is raised only by branches `EnvManager` itself owns. Tests assert the exact propagated type. |
| R4 | A `pypi:` hook accidentally reaches `resolve_source` (whose `PyPISource` branch raises `SourceResolutionError`), producing the wrong error type / a misleading message (AC-7). | Low | Med — wrong error domain. | The `match` routes `PyPISource()` straight to `EnvError` **before** any `resolve_source` call; `resolve_source` is invoked only for `SystemSource` / `ProjectSource`. Acceptance test asserts `EnvError` (not `SourceResolutionError`) and that no subprocess is spawned. |
| R5 | `shlex.split` on an empty / whitespace-only `run` returns `[]` and an `IndexError` escapes instead of `EnvError` (AC-9). | Low | Med — opaque crash. | `_derive_tool` checks for the empty list and catches `ValueError` (unbalanced quotes) explicitly, raising `EnvError` with the hook id + the offending `run`. Dedicated tests for both. |
| R6 | `cache_key` material drifts from AC-4's exact string, breaking STY-0009 explainability. | Low | High — cross-story contract break. | The exact material (`"\n".join([_CACHE_KEY_SCHEME, origin, str(executable)])`, UTF-8, SHA-256 hexdigest) is localized in one private `_cache_key` helper and pinned by AC-4/AC-5/AC-6 tests. |
