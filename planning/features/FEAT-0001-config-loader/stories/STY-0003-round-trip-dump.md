---
id: STY-0003
title: Round-trip dump for hooksmith migrate output
status: Draft
owner: TBD
date: 2026-05-29
feature: FEAT-0001
---

# STY-0003: Round-trip dump for `hooksmith migrate` output

## As a / I want / So that

As a **hooksmith developer**, I want **a `dump_config(config, path)` function
that writes a valid `check.toml`** so that **`hooksmith migrate` can produce
TOML output from an in-memory `HooksmithConfig` without hand-rolling
serialization**.

## Scope

STY-0001 and STY-0002 gave us the read side. This story gives us the write
side. The function lives in a new module `src/hooksmith/config/dumper.py` and
is exported from the public `hooksmith.config` facade. It is the only primitive
`hooksmith migrate` needs in order to produce its output — the full
YAML→TOML migration workflow (parsing `.pre-commit-config.yaml`, known-hook
mapping, CLI wiring in `migrate.py`) is explicitly deferred to a later story.

The dumped TOML must use the idiomatic TOML constructs that `check.toml`
already uses: `[[hook]]` array-of-tables headers, `[group.<name>]`
dotted-table headers, and inline-table syntax for `when = { ... }`. All
`None` fields and fields at their default values are omitted so the output
stays clean and human-editable.

## Tasks

- [ ] TSK-001: Write `src/hooksmith/config/dumper.py` with
  `dump_config(config: HooksmithConfig, path: Path) -> None`.
- [ ] TSK-002: Update `src/hooksmith/config/__init__.py` to export
  `dump_config`; update `__all__`.
- [ ] TSK-003: Write `tests/unit/test_config_dumper.py` (≥ 15 unit tests).
- [ ] TSK-004: Write `tests/integration/test_config_dump_acceptance.py`
  (4–6 acceptance tests).
- [ ] TSK-005: Update `docs/config/reference.md` with a `dump_config` section.

## Acceptance criteria

- [ ] AC-1: `dump_config(load_config(p), p2)` then `load_config(p2)` equals
  `load_config(p)` (round-trip fidelity).
- [ ] AC-2: Dumped text is valid TOML — `tomllib.loads(text)` does not raise.
- [ ] AC-3: `[[hook]]` entries use TOML array-of-tables syntax.
- [ ] AC-4: `[group.<name>]` entries use TOML dotted-table syntax.
- [ ] AC-5: `when = { … }` is serialized as an inline table, not a sub-table.
- [ ] AC-6: `None` fields are absent from dumped output.
- [ ] AC-7: Fields at their default values are absent from dumped output.
- [ ] AC-8: `from hooksmith.config import dump_config, load_config` works.
- [ ] AC-9: `mypy --strict src/hooksmith/config/` passes with no new errors.
- [ ] AC-10: No new runtime dependencies added.

## Notes

- `tomlkit` is already a runtime dep — use `tomlkit.document()`,
  `tomlkit.aot()`, `tomlkit.table()`, `tomlkit.inline_table()` for TOML
  construction.
- `HookDef.from_` has alias `from` — `model_dump(by_alias=True)` produces
  the correct TOML key.
- Function must be synchronous and side-effect-free beyond writing `path`.
- `migrate.py` stub (`raise NotImplementedError`) is intentionally left
  unchanged — full YAML→TOML migration is a later story.
