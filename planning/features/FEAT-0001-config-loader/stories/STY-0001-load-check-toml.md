---
id: STY-0001
title: Load check.toml into a validated model
status: Draft
owner: TBD
date: 2026-05-28
feature: FEAT-0001
---

# STY-0001: Load `check.toml` into a validated model

## As a / I want / So that

As a **hooksmith developer**, I want **a `load_config(path)` function that returns a fully typed `HooksmithConfig`** so that **every other subsystem can rely on the config being shape-valid before it runs**.

## Scope

The happy path only: a well-formed `check.toml` parses into a pydantic model that mirrors the documented schema. Error messaging is good enough to debug obvious mistakes (missing required fields, wrong types) but is hardened in STY-0002.

## Tasks

- [ ] TSK-001 Define `HookDef`, `SourceSpec`, `GroupDef`, `HooksmithConfig` as pydantic models in `src/hooksmith/config/schema.py`.
- [ ] TSK-002 Implement `load_config(path: Path) -> HooksmithConfig` in `src/hooksmith/config/loader.py` using stdlib `tomllib`.
- [ ] TSK-003 Add a fixture `tests/fixtures/check.toml.sample` matching the project's own `check.toml`.
- [ ] TSK-004 Write `tests/unit/test_config_loader.py` covering: load sample, missing required key fails, unknown key warns or fails per pydantic config.
- [ ] TSK-005 Add a usage example to `docs/config/reference.md` showing the Python API.

## Acceptance criteria

- [ ] `pytest tests/unit/test_config_loader.py` passes with ≥ 90% line coverage on `hooksmith.config`.
- [ ] `python -c "from hooksmith.config import load_config; print(load_config('check.toml'))"` against the repo's own `check.toml` prints a non-empty `HooksmithConfig`.
- [ ] `mypy src/hooksmith/config/` passes with no errors under the project's strict settings.
- [ ] No new runtime dependency added beyond `pydantic>=2` (already pinned).

## Notes

- Use `tomllib` (stdlib, 3.11+) — no need for `tomli` since the project requires Python 3.11.
- Pydantic's `ValidationError` already includes the offending key path; STY-0002 will translate that path into a file:line:col location using `tomllib`'s position info.
- Keep `load_config` synchronous and side-effect-free — async I/O is not warranted here.
