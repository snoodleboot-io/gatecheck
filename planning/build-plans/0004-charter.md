---
id: BUILD-0004-CHARTER
title: Build charter for STY-0004 (parse + classify source specs)
parent: BUILD-0004
target_story: STY-0004
status: Locked
date: 2026-06-28
---

# BUILD-0004 Charter — STY-0004 (Parse & classify a hook's source spec)

## Goal

Give a hook's `from` string *meaning*. Deliver a pure, synchronous
`parse_source(spec: str) -> ParsedSource` function in a **new** package
`src/hooksmith/sources/` that classifies a `from` spec into one of four typed,
frozen, `kind`-discriminated models — `PyPISource`, `ProjectSource`,
`SystemSource`, `UnsupportedSource` — that downstream resolution (STY-0005) and
the runner can `match` on without re-parsing the raw string. Bad specs raise a
dedicated `SourceSpecError(ValueError)`; when the spec originated from a loaded
`check.toml`, the **config layer** re-raises that error as the existing
`ConfigError` with `check.toml:LINE:COL:` context, reusing STY-0002's
`(line, col, msg)` machinery so users get the same IDE-parseable diagnostics
they already get for the rest of the config.

This is the first vertical slice of FEAT-0002: **parse only — no network, no
venv creation, no executable resolution.** See
[STY-0004](../features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md),
[FEAT-0002](../features/FEAT-0002-source-resolution/feature.md),
[PRD-0001 § Scope — Sources](../prd/0001-hooksmith.md#scope), and
[ADR-0001](../adr/0001-python-host-rust-core.md).

## In-scope for this build

- New package `src/hooksmith/sources/` (one class per file, per core
  conventions):
  - `pypi_source.py` — `PyPISource` frozen model.
  - `project_source.py` — `ProjectSource` frozen model.
  - `system_source.py` — `SystemSource` frozen model.
  - `unsupported_source.py` — `UnsupportedSource` frozen model.
  - `parsed_source.py` — the `ParsedSource` discriminated-union type alias.
  - `source_spec_error.py` — `SourceSpecError(ValueError)`.
  - `parser.py` — `parse_source(spec) -> ParsedSource`.
  - `__init__.py` — facade exporting the public symbols; sets `__all__`.
- Wire `check.toml` → `ConfigError` translation: parse every `HookDef.from_`
  during `load_config` and re-raise `SourceSpecError` as `ConfigError` with the
  offending hook's `from`-key `line:col`, recovered via the existing
  `_error_translator` helpers.
- Unit tests in `tests/unit/test_source_parse.py` (≥ 15 tests).
- Acceptance tests in `tests/integration/test_source_spec_acceptance.py`
  (4–6 tests).
- "Parsed source model" subsection added to
  `docs/config/reference.md § Source spec syntax`.

## Out of scope (deferred)

- **Resolving `project` / `system` to a concrete executable** — STY-0005.
  `parse_source` classifies; it does not touch the filesystem, `PATH`, or any
  venv.
- **PyPI / private-registry network resolution and venv creation** — STY-0006 /
  Environments. `PyPISource` is a validated *request*; no index is contacted.
- **PEP 508 / version-range validation of `requirement`** — carried through
  verbatim; validation is resolution's concern.
- **Lighting up `local:` / `git:` / `docker:`** — recognized as
  `UnsupportedSource(scheme=…)` only; full support is later FEAT-0002 work.
- **The cache key / hit-miss explainability** — PRD-0001 § Scope — Cache.
- **New runtime dependencies** — none added; pydantic (already present since
  STY-0001) is sufficient.

## Success criteria

Verbatim from
[STY-0004](../features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md)
Acceptance criteria:

- [ ] AC-1: `parse_source("project")` → `ProjectSource`;
  `parse_source("system")` → `SystemSource`.
- [ ] AC-2: `parse_source("pypi:ruff>=0.4,<1")` →
  `PyPISource(requirement="ruff>=0.4,<1", registry=None)`.
- [ ] AC-3: `parse_source("pypi+internal:org-linter==2.1.0")` →
  `PyPISource(requirement="org-linter==2.1.0", registry="internal")`.
- [ ] AC-4: `parse_source("local:scripts/lint.py")`,
  `"git:https://x@v1"`, `"docker:img:tag"` each →
  `UnsupportedSource(scheme=…)` and do **not** raise.
- [ ] AC-5: Invalid specs raise `SourceSpecError`: empty/whitespace,
  `"project:x"`, `"pypi:"` (empty requirement), `"pypi+:ruff"` (empty alias),
  `"bogus:thing"` (unknown scheme), `"ruff"` (bare word).
- [ ] AC-6: `SourceSpecError` subclasses `ValueError`; its message has the form
  `invalid source spec '<spec>': <reason>`.
- [ ] AC-7: The returned model is a `Literal`-discriminated union usable in a
  `match` over `.kind` without re-inspecting the raw string.
- [ ] AC-8: A `check.toml` with a bad hook `from` raises `ConfigError` whose
  first line matches `^check\.toml:\d+:\d+:` and names the bad spec.
- [ ] AC-9: `parse_source` performs no I/O — no filesystem, no network, no
  subprocess.
- [ ] AC-10: `from hooksmith.sources import parse_source, ParsedSource,
  SourceSpecError` works.
- [ ] AC-11: `mypy --strict src/hooksmith/sources/` passes with no new errors.
- [ ] AC-12: No new runtime dependencies added.

## Stakeholder dependencies

- **[STY-0001](../features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md)**
  — merged into `main`; provides `HooksmithConfig`, `HookDef` (`from_` alias
  `from`), and `load_config`. No blocker.
- **[STY-0002](../features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md)**
  — merged into `main`; provides `ConfigError(path, [(line, col, msg)])` and the
  `_error_translator` helpers (`_anchor_line`, `_nth_aot_header_line`,
  `_scan_field`) that TSK-005 reuses to recover the `from`-key `line:col`. No
  blocker; **this is the integration surface and must not be reshaped.**
- **pydantic (>=2)** — already a runtime dep since STY-0001. No new
  installation required. No blocker.
- **Locked architecture:**
  [0004-architecture-decision.md](0004-architecture-decision.md) — Lanes
  consume it; any change re-opens BUILD-0004.

## Cross-references / baseline issues (architect recommendation, user decides)

- **`src/hooksmith/env/manager.py:13`** imports
  `from hooksmith.config.schema import HookDef`, but no `config/schema.py`
  exists (the real module is `config/hook_def.py`). This currently fails
  `mypy --strict`. **Recommendation: fix now, IN BUILD-0004** as a one-line
  import correction (`from hooksmith.config.hook_def import HookDef`).
  Rationale: `env/manager.py` is the direct downstream consumer of FEAT-0002's
  source/env work (it is where STY-0005 will call `parse_source`), it is broken
  today, the fix is trivial and isolated, and leaving it red muddies the
  `mypy --strict` gate for this build. See architecture-decision §10.
- **`src/hooksmith/core.py:11`** carries a `# type: ignore[import-not-found]`
  on the `hooksmith_core` Rust-extension import that `mypy` may flag as unused
  when the wheel is absent. **Recommendation: OUT of scope (defer).** Rationale:
  it is unrelated to source-spec parsing, sits on the Rust-core boundary
  (ADR-0001) that FEAT-0002 explicitly does not touch, and STY-0004 is a
  pure-Python slice. Address it under a runner/core story. See
  architecture-decision §10.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | `from`-key `line:col` recovery for a bad spec re-implements (and diverges from) STY-0002's scanner. | Med | High — diagnostics drift from the rest of the loader; AC-8 regex passes but column is wrong. | TSK-005 MUST call the existing `_error_translator` helpers (`_nth_aot_header_line` to anchor the Nth `[[hook]]`, `_scan_field` to locate `from =`), not hand-roll a scan. Acceptance tests assert exact `(line, col)` on a fixture with a known-position bad `from`. |
| R2 | Eager parse-at-load changes `load_config`'s observable failure surface (a previously-valid model now raises). | Med | Med — callers that loaded configs with `local:`/`git:` specs see new behaviour. | Eager validation only raises for **invalid** specs; `UnsupportedSource` does NOT raise (it is valid-but-unsupported). Document the eager-vs-lazy decision (§5); acceptance tests confirm a `local:` `from` loads without error. |
| R3 | Name collision with existing `hooksmith.config.SourceSpec` (the `[sources]` table). | Low | Med — import confusion, accidental conflation of registry-config and parsed-spec concepts. | New package `hooksmith.sources`; union is `ParsedSource`, never `SourceSpec`. No symbol named `SourceSpec` is exported from `hooksmith.sources`. |
| R4 | Discriminated-union `match` fails to narrow under `mypy --strict`. | Low | Med | Use a pydantic `Annotated[Union[...], Field(discriminator="kind")]` `TypeAdapter` only inside the parser; the public `ParsedSource` is a plain `Union` alias so `match … case PyPISource()` narrows cleanly. AC-11 gate catches regressions. |
