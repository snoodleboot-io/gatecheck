---
id: BUILD-0003-CHARTER
title: Build charter for STY-0003 (round-trip config dump)
parent: BUILD-0003
target_story: STY-0003
status: Locked
date: 2026-05-29
---

# BUILD-0003 Charter — STY-0003 (Round-trip config dump)

## Goal

Deliver a synchronous `dump_config(config: HooksmithConfig, path: Path) -> None`
function — the write-side complement to `load_config` — that serializes a
`HooksmithConfig` back to a valid, human-readable `check.toml` on disk. The
function uses `tomlkit` document-building primitives to produce the idiomatic
TOML structural conventions (`[[hook]]` array-of-tables headers, dotted
`[group.<name>]` headers, inline `when = { … }` tables) that the project's
own `check.toml` uses. This is the primitive that `hooksmith migrate` will
call to produce its output, unblocking the migration story without coupling
serialization logic to the CLI layer. See
[STY-0003](../features/FEAT-0001-config-loader/stories/STY-0003-round-trip-dump.md),
[FEAT-0001](../features/FEAT-0001-config-loader/feature.md), and
[PRD-0001 § Migration](../prd/0001-hooksmith.md#scope).

## In-scope for this build

- New `src/hooksmith/config/dumper.py` with
  `dump_config(config: HooksmithConfig, path: Path) -> None`.
- Export `dump_config` from `src/hooksmith/config/__init__.py`; update
  `__all__`.
- Acceptance tests in `tests/integration/test_config_dump_acceptance.py`
  (4–6 tests).
- Unit tests in `tests/unit/test_config_dumper.py` (≥ 15 tests).
- `dump_config` section added to `docs/config/reference.md`.

## Out of scope (deferred)

- Full `hooksmith migrate` YAML→TOML transform — `migrate.py` stub is left
  unchanged; the complete migration story is a separate, later story.
- Atomic write / crash-safe semantics (direct write is sufficient for
  STY-0003).
- Pretty-printing or comment preservation in output.
- New runtime dependencies — `tomlkit` (already present since STY-0002) is
  sufficient; no additional serialization library is introduced.

## Success criteria

Verbatim from [STY-0003](../features/FEAT-0001-config-loader/stories/STY-0003-round-trip-dump.md) Acceptance criteria:

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

## Stakeholder dependencies

- **[STY-0001](../features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md)**
  — already merged into `main`; provides `HooksmithConfig`, `HookDef`,
  `GroupDef`, `SourceSpec`, and `load_config`. No blocker.
- **[STY-0002](../features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md)**
  — already merged into `main`; provides `ConfigError` and adds
  `tomlkit>=0.13` as a runtime dep (`0.15.0` confirmed installed). No blocker.
- **`tomlkit>=0.13`** — already a runtime dep; no new installation required.
  No blocker.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | `when` inline-table construction — `tomlkit.inline_table()` must be used; an expanded sub-table would fail AC-5 and break the `load_config` round-trip. | Med | High — round-trip fidelity breaks for any hook with a `when` field. | Lane C unit tests assert the raw `tomlkit` document `as_string()` contains `when = {` before the full `dump_config` integration runs; assert `tomllib.loads(dumped)` equals `tomllib.loads(original)` on a fixture with a `when` field. |
| R2 | Default-field exclusion — `exclude_defaults=True` in `model_dump` may need tuning; tests pin the expected omission behaviour to prevent fields from silently disappearing or appearing. | Low | Med — fields silently drop or appear in dumped config depending on pydantic version behaviour. | Use `field_info.default` (not a hardcoded comparison) and compare with `is` for booleans. Dedicated unit tests per boolean field assert presence/absence explicitly. |
| R3 | `from_` keyword alias — `model_dump(by_alias=True)` must yield key `"from"` not `"from_"`; a Lane C test explicitly asserts `"from_"` does NOT appear and `"from "` DOES appear, locking this against regression. | Med | High — round-trip acceptance test AC-1 fails for every hook if the wrong key is emitted. | Integration round-trip test AC-1 catches any regression on the full fixture; unit test asserts key name directly on the tomlkit document string. |
