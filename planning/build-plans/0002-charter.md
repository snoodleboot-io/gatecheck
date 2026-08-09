---
id: BUILD-0002-CHARTER
title: Build charter for STY-0002 (file:line:col error context)
parent: BUILD-0002
target_story: STY-0002
status: Locked
date: 2026-05-28
---

# BUILD-0002 Charter — STY-0002 (file:line:col error context)

## Goal

Wrap `load_config`'s raw `tomllib.TOMLDecodeError` and `pydantic.ValidationError`
exits in a single `ConfigError` whose `__str__` emits one
`check.toml:LINE:COL: <message>` line per underlying error — the same prefix
format IDE error matchers and `grep -nE` already understand. STY-0001 produced
the right values; STY-0002 makes those values point users at the exact byte
they need to edit. See
[STY-0002](../features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md),
[FEAT-0001](../features/FEAT-0001-config-loader/feature.md),
[PRD-0001](../prd/0001-hooksmith.md), and
[ADR-0001](../adr/0001-python-host-rust-core.md).

## In-scope for this build

- Add `tomlkit>=0.13` to `[project].dependencies` (only new dep).
- New `ConfigError(ValueError)` in `src/hooksmith/config/config_error.py` carrying `(path, [(line, col, msg), ...])`.
- New private `_error_translator.py` with `_parse_toml_error` and `_locate_validation_error` helpers.
- Modify `load_config` to catch both raw exceptions, translate, and re-raise `ConfigError` with `__cause__` preserved.
- Export `ConfigError` from `hooksmith.config.__init__`.
- Acceptance + unit tests; two-layer assertions on existing STY-0001 tests.

## Out of scope (deferred)

- Multi-file `check.toml` merging — separate monorepo feature under [FEAT-0001](../features/FEAT-0001-config-loader/feature.md) "Out of scope".
- `from`-string spec parsing (`pypi:`, `git:`) — blocked on the source-resolver story; errors don't exist yet.
- ANSI/Rich coloured output — `hooksmith run` may layer styling later; charter format stays plain text.
- Adding position info to surfaces STY-0001 left untouched (e.g. `__init__.py` re-exports, model construction outside `load_config`).
- Round-trip dump (`hooksmith migrate`) — STY-0003.

## Success criteria

Verbatim from [STY-0002](../features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md) Acceptance criteria:

- [ ] `load_config(Path("malformed.toml"))` where `malformed.toml` is `[unclosed` raises `ConfigError`; `str(exc)` first line matches `check\.toml(\.[a-z]+)?:\d+:\d+:\s+`.
- [ ] `load_config(Path("missing_id.toml"))` with `[[hook]]\nfrom = "x"\nrun = "x"\n` raises `ConfigError`; `str(exc)` contains the offending table's line and mentions field name `id`.
- [ ] A file with TWO independent ValidationErrors surfaces both, separated by newline; `str(exc).count("\n") >= 1`.
- [ ] `ConfigError` subclasses `ValueError` — existing `except ValueError:` callers still work.
- [ ] `from hooksmith.config import ConfigError, load_config` works.
- [ ] `pytest tests/unit/test_config_error.py` ≥ 90% line coverage on `_error_translator` and `config_error`.
- [ ] `mypy --strict src/hooksmith/config/` still passes.
- [ ] Only `tomlkit>=0.13` added as runtime dep.
- [ ] All STY-0001 tests still pass — including raw-exception tests, now asserting `ConfigError.__cause__` is the raw `TOMLDecodeError` / `ValidationError` (two-layer strategy).

## Stakeholder dependencies

- **[STY-0001](../features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md)** — already merged into `main`; provides the loader + models STY-0002 wraps. No blocker.
- **`tomlkit>=0.13`** — on PyPI, installed in venv at G0 (v0.15.0), 100+ KLOC battle-tested. No blocker.
- **Downstream consumers of `ConfigError` format** — the future `hooksmith run` CLI error display will format these strings to users; locking the `path:line:col: msg` shape now is what unblocks them. No party blocks STY-0002.
- **Locked user decisions (BUILD-0002):** (1) add `tomlkit` for exact positions; (2) two-layer test strategy (keep raw-exception tests + add wrapper tests); (3) same multiagent pattern as STY-0001. No re-litigation.
- **Convention exceptions** G-1…G-9 from BUILD-0001 carry forward unchanged.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | `tomlkit` exposes positions via round-trip text search, not attributes — accuracy on edge cases (escaped strings, nested arrays, AoT entries) depends on search correctness. | Med | High — wrong line numbers mislead users worse than no line numbers. | Lane C tmp_path fixtures with known line numbers per edge case (nested arrays, escaped quotes, multiple `[[hook]]` blocks); assert exact `(line, col)` in tests. |
| R2 | `pydantic.ValidationError.errors()` order may shift across pydantic patch versions, making multi-error tests flaky. | Med | Med — CI green-then-red on unrelated upgrades. | Pin assertion order via field-name selection (`sorted(errors, key=lambda e: e["loc"])` in test, or `any(... for e in errors)`), never by document position. |
| R3 | `ConfigError(ValueError)` subclassing — callers using `except (TOMLDecodeError, ValidationError):` (not `ValueError`) silently lose their handler when STY-0002 ships. | Low | Med — silent semantic break in third-party code. | `ConfigError` sets `__cause__` to the raw exception (`raise ConfigError(...) from err`); enforcement-agent + Lane C tests verify both `isinstance(exc, ValueError)` and `isinstance(exc.__cause__, TOMLDecodeError | ValidationError)` so both layers stay observable. |
