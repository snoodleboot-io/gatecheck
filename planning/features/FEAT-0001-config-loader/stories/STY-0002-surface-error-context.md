---
id: STY-0002
title: Surface schema errors with file/line context
status: Draft
owner: TBD
date: 2026-05-28
feature: FEAT-0001
---

# STY-0002: Surface schema errors with file/line context

## As a / I want / So that

As a **hooksmith user editing my `check.toml`**, I want **error messages that
include `check.toml:LINE:COL:` prefixes** so that **my IDE and shell pipelines
(grep, sed, vim quickfix) can jump straight to the offending line — same
ergonomics as a compiler error**.

## Scope

STY-0001 left `load_config` raising raw `tomllib.TOMLDecodeError` and
`pydantic.ValidationError`. Neither produces the file-prefixed format that
IDE error matchers expect. This story:

1. Adds **`tomlkit>=0.13`** as a runtime dependency. `tomlkit` parses TOML
   while preserving source positions on every element — required for exact
   `line:col` reporting on deeply nested `ValidationError`s.
2. Adds a `ConfigError` exception in `hooksmith.config` that carries one or
   more `(line, col, message)` tuples.
3. Catches `TOMLDecodeError` and `ValidationError` inside `load_config`,
   translates each into one or more `ConfigError` entries, and re-raises a
   single `ConfigError` whose `__str__` is a newline-separated list of
   `check.toml:LINE:COL: <message>` lines.
4. For `TOMLDecodeError` (Python 3.11 has no public `lineno`/`colno`):
   regex-extract `at line N, column M` from `str(err)`; fall back to `1:1` if
   the parser used a non-positional message like "at end of document".
5. For `ValidationError`: walk the `loc` tuple into the `tomlkit` document
   tree, then use the element's `as_string()` round-trip text plus its
   surrounding table context to locate it in the original source. `tomlkit`
   doesn't expose explicit `lineno`/`colno` attributes — its value is that
   it preserves the exact source text per element, which lets a
   tomlkit-assisted search resolve positions reliably at every nesting depth
   (without the brittle "guess the key location" of a pure file scan).

Surface remains unchanged for callers that don't care about position info —
`ConfigError` subclasses `ValueError` so existing `except ValueError:` blocks
still catch it.

The architecture sketch §5 explicitly deferred this work to STY-0002; this
story closes that note.

## Parsing strategy

Two valid approaches; architect picks one in BUILD-0002:

- **Option A — always tomlkit**: `tomlkit.parse(text)` returns a `TOMLDocument`
  that behaves like a dict (passes to `model_validate` cleanly) AND carries
  positions. One parse, slightly slower than stdlib `tomllib`.
- **Option B — tomllib happy path, tomlkit on error**: parse with stdlib
  `tomllib` for speed; on `ValidationError`, re-parse the source with
  `tomlkit` and walk to the offending `loc` for positions. Faster happy
  path, two parses on error.

Either is acceptable per acceptance criteria; architect should pick based on
benchmark cost.

## Out of scope

- Multi-file config merging (different story, monorepo feature).
- Translation of `from`-string spec errors (`pypi:`, `git:`, etc.) — those
  errors don't exist until the source-resolver story ships.
- Coloured/styled output. The format is plain text so it works in CI logs and
  IDE matchers. `hooksmith run` may layer Rich-style colouring on top later.

## Tasks

- [ ] TSK-001 Add `tomlkit>=0.13` to `[project].dependencies` in
  `pyproject.toml`.
- [ ] TSK-002 Define `class ConfigError(ValueError)` in
  `src/hooksmith/config/config_error.py`. Carries `path: Path`, `errors:
  list[tuple[int, int, str]]`. `__str__` joins entries as
  `f"{path}:{line}:{col}: {msg}"` separated by newlines.
- [ ] TSK-003 Implement `_parse_toml_error(err: TOMLDecodeError) -> tuple[int,
  int, str]` in `src/hooksmith/config/_error_translator.py` (private module —
  leading underscore). Regex-match `at line (\d+), column (\d+)` from
  `str(err)`; fall back to `(1, 1, str(err))`.
- [ ] TSK-004 Implement `_locate_validation_error(err: ValidationError,
  source: str, toml_doc: tomlkit.TOMLDocument) -> list[tuple[int, int, str]]`
  in the same private module. For each error in `err.errors()`:
  - Walk `loc` into `toml_doc` to retrieve the offending element.
  - Use `element.as_string()` (or its parent table's `as_string()`) as a
    search target against `source` to compute the 1-based `(line, col)` of
    the first match.
  - For AoT (`[[hook]]`) entries, count `[[hook]]` headers in `source` to
    pick the right Nth match.
  Return `(line, col, formatted_message)` per error.
- [ ] TSK-005 Modify `load_config` per architect-chosen parsing strategy
  (Option A or B in §Parsing strategy):
  - Catch `TOMLDecodeError` → raise `ConfigError(path, [_parse_toml_error(e)])`
  - Catch `ValidationError` → raise `ConfigError(path, _locate_validation_error(e, doc))`
- [ ] TSK-006 Update `__init__.py` to export `ConfigError`. New public API:
  `["ConfigError", "HooksmithConfig", "GroupDef", "HookDef", "SourceSpec", "load_config"]`.
- [ ] TSK-007 Update `docs/config/reference.md` "Error handling" subsection to
  reflect the new `ConfigError` exception (and that older callers catching
  `ValueError` still work).
- [ ] TSK-008 Update `planning/build-plans/0001-architecture-sketch.md` §5
  table: add a row noting `ConfigError` wraps the two raw exception types.
  Add note that STY-0002 introduces `tomlkit` runtime dep (supersedes
  STY-0001's no-new-dep stance, which was scoped to STY-0001).

## Acceptance criteria

- [ ] `load_config(Path("malformed.toml"))` where `malformed.toml` is
  `[unclosed` raises `ConfigError`. `str(exc)` first line matches
  `check\.toml(\.[a-z]+)?:\d+:\d+:\s+`.
- [ ] `load_config(Path("missing_id.toml"))` where `missing_id.toml` has
  `[[hook]]\nfrom = "x"\nrun = "x"\n` raises `ConfigError`. `str(exc)`
  contains the offending table's line and mentions the field name `id`.
- [ ] `load_config(...)` on a file with TWO independent ValidationErrors
  surfaces both, separated by newline. `str(exc).count("\n") >= 1`.
- [ ] `ConfigError` subclasses `ValueError` — existing `except ValueError:`
  callers continue to work without code changes.
- [ ] `from hooksmith.config import ConfigError, load_config` works.
- [ ] `pytest tests/unit/test_config_error.py` (new file) ≥ 90 % line coverage
  on `hooksmith.config._error_translator` and `hooksmith.config.config_error`.
- [ ] `mypy --strict src/hooksmith/config/` continues to pass.
- [ ] Runtime dependency added: **only** `tomlkit>=0.13` (no other new deps).
- [ ] All STY-0001 tests still pass — including the **raw-exception-layer
  tests**, which now assert that `ConfigError`'s `__cause__` is the raw
  `TOMLDecodeError` / `ValidationError`. Both the raw and wrapped layers are
  exercised (two-layer test strategy per user decision).

## Notes

- Python 3.11/3.12 `tomllib.TOMLDecodeError` exposes line/column only inside
  the string message — no public attributes. Python 3.13 added `lineno` and
  `colno` directly. We parse the string for now; a future story may swap to
  the attributes once we bump the minimum to 3.13.
- `tomlkit` was chosen over the file-scan heuristic per user decision — exact
  positions at every nesting depth justify the +~200 KB install cost.
- Multiple errors per file: pydantic's `ValidationError.errors()` already
  returns a list; we emit one line per entry in the same order.
- **Two-layer test strategy.** Existing STY-0001 tests that asserted on
  `pytest.raises(tomllib.TOMLDecodeError)` / `pytest.raises(pydantic.ValidationError)`
  are KEPT and updated to use `pytest.raises(ConfigError) as exc_info` plus
  `assert isinstance(exc_info.value.__cause__, TOMLDecodeError)` (or the
  corresponding `ValidationError`). This locks both the wrapper layer
  (STY-0002) and the underlying raw-exception identity (STY-0001) in one
  assertion. New STY-0002-specific tests in `test_config_error.py` cover the
  `ConfigError` formatting, multi-error case, and position-extraction logic
  exhaustively.
