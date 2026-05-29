---
id: BUILD-0001-CHARTER
title: Build charter for STY-0001 (Config Loader)
parent: BUILD-0001
target_story: STY-0001
status: Locked
date: 2026-05-28
---

# BUILD-0001 Charter — STY-0001 (Config Loader)

## Goal

Deliver a synchronous, side-effect-free `load_config(path)` function that parses a project's
`check.toml` into a fully typed, pydantic-validated `GatecheckConfig`. This is the foundation
every downstream gatecheck subsystem (sources, environments, runner, workspace) reads from, so
shape-validity must be guaranteed at the boundary before anything else runs. See
[STY-0001](../features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md),
[FEAT-0001](../features/FEAT-0001-config-loader/feature.md), and
[PRD-0001 § Scope — Config](../prd/0001-gatecheck.md#scope).

## In-scope for this build

- Define `HookDef`, `SourceSpec`, `GroupDef`, `GatecheckConfig` as pydantic v2 models (one class per file per BUILD-0001 §1.2 C4).
- Implement `load_config(path: Path) -> GatecheckConfig` using stdlib `tomllib`.
- Fixture `tests/fixtures/check.toml.sample` that mirrors the repo's own `check.toml`.
- Unit tests covering happy path, missing required key, unknown key behavior.
- Usage snippet in `docs/config/reference.md` documenting the Python API.
- Preserve the documented public import surface `from gatecheck.config import load_config, GatecheckConfig` (facade exception per BUILD-0001 G-3).

## Out of scope (deferred)

- Human-friendly `check.toml:LINE:COL:` error formatting — **STY-0002**.
- Round-trip dump for `gatecheck migrate` output — **STY-0003**.
- Monorepo merging of multiple `check.toml` files — separate feature under [FEAT-0001](../features/FEAT-0001-config-loader/feature.md) "Out of scope".
- Source-spec resolution against PyPI — separate feature.
- Live reload on file change — separate feature.
- Any runtime coupling to the Rust core (`gatecheck_core`) — explicitly forbidden by [FEAT-0001](../features/FEAT-0001-config-loader/feature.md) Acceptance.

## Success criteria

Verbatim from [STY-0001](../features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md) Acceptance criteria:

- [ ] `pytest tests/unit/test_config_loader.py` passes with ≥ 90% line coverage on `gatecheck.config`.
- [ ] `python -c "from gatecheck.config import load_config; print(load_config('check.toml'))"` against the repo's own `check.toml` prints a non-empty `GatecheckConfig`.
- [ ] `mypy src/gatecheck/config/` passes with no errors under the project's strict settings.
- [ ] No new runtime dependency added beyond `pydantic>=2` (already pinned).

## Stakeholder dependencies

- **[PRD-0001](../prd/0001-gatecheck.md)** — establishes the Python-host project shape and config-first design; settled, no PM action required.
- **[ADR-0001](../adr/0001-python-host-rust-core.md)** — locks the Python-host / Rust-core split that justifies keeping the loader on the Python side; immutable.
- **[FEAT-0001](../features/FEAT-0001-config-loader/feature.md)** — parent feature; STY-0002 and STY-0003 depend on this story's models and public API and cannot start until BUILD-0001 lands.
- **architect-agent (Lane A peer)** — must publish `planning/build-plans/0001-architecture-sketch.md` to lock the API contract before Lanes B/C/D can produce conformant artifacts (gate G1).
- **devops-agent (Lane ENV)** — G0 already GREEN per session log (Python 3.11.15 venv, pydantic v2, mypy, ruff, pytest, mutmut, watcher); no further env unblocking required from this charter.
- **Documented exceptions in force:** G-2 (CONTRIBUTING.md branch naming authoritative), G-3 (`__init__.py` facade exception), G-4 (one-class-per-file split), G-8 (venv pinned to 3.11) — all locked in session.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | The repo's own `check.toml` exercises schema shapes the sample fixture doesn't, so the integration assertion in acceptance criterion #2 passes against the fixture but fails against the real file. | Med | High — false-green at G2. | Lane E `fixture_subagent` diffs `check.toml.sample` against the repo `check.toml` and expands the fixture to cover every section/key shape before Lane B's acceptance test runs. |
| R2 | Pydantic v2 default `extra="ignore"` silently drops unknown keys, making STY-0001 task TSK-004 ("unknown key warns or fails") untestable and quietly weakening the contract STY-0002 needs to build on. | Med | Med — degrades downstream story. | Architect sketch must specify `model_config = ConfigDict(extra="forbid")` on every model; enforcement-agent checks at G3; unit_subagent_schema asserts the rejection explicitly. |
| R3 | Coverage acceptance bar (≥ 90% line on `gatecheck.config`) is measured against the package including the `__init__.py` facade; trivial re-export lines can drag the percentage just below the gate. | Low | Med — gate-flip late in pipeline. | `pyproject.toml` `[tool.coverage.report] exclude_lines` updated to skip pure re-export lines, OR acceptance test invokes `pytest --cov=gatecheck.config --cov-report=term-missing` and asserts on `Missing:` being empty for non-`__init__` modules — decision deferred to architect, flagged here so it isn't discovered at G2. |
