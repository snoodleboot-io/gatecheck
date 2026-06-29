---
id: STY-0004
title: Parse and classify a hook's source spec into a typed model
status: Draft
owner: TBD
date: 2026-06-28
feature: FEAT-0002
prd: PRD-0001 § Scope — Sources
adrs: [ADR-0001]
---

# STY-0004: Parse and classify a hook's source spec into a typed model

## As a / I want / So that

As a **gatecheck developer**, I want **a `parse_source(spec)` function that
turns a hook's `from` string into a typed, validated source-kind object** so
that **the resolver and runner can `match` on the kind without re-parsing the
raw string, and bad specs are rejected with a clear, IDE-parseable error
instead of failing deep inside environment resolution**.

## Scope

FEAT-0001 gave us a validated `check.toml` model in which `HookDef.from_` is
nothing more than a non-empty string. This story gives that string *meaning*:
it parses and classifies the spec into one of the documented kinds and
validates its syntax — **pure parsing only. NO network, NO venv creation, NO
executable resolution.** Resolving `project`/`system` to a binary is STY-0005;
network resolution of `pypi:` is STY-0006 / Environments.

The new code lives in a new package `src/gatecheck/sources/` (not under
`gatecheck.config`). Rationale: the existing `gatecheck.config.SourceSpec`
model already names the `[sources]` *table* (registry config), so reusing
`config` for the parsed-spec model would collide on the name and conflate two
distinct concepts — "what registries exist" vs "what a single hook's `from`
points at". Source classification is also the entry point for FEAT-0002's
resolution work, which is explicitly a non-config concern. The package exposes
a single public function, `parse_source`, and the typed model it returns.

### Parse rules (per kind)

The `from` string is matched in this order; the first rule that matches wins.
Matching is case-sensitive and the whole string (after `str.strip()` of
surrounding whitespace) must be consumed.

| Input | Kind | Parsed fields |
|---|---|---|
| `project` | project | (none) |
| `system` | system | (none) |
| `pypi:<spec>` | pypi | `requirement = "<spec>"`, `registry = None` |
| `pypi+<alias>:<spec>` | pypi | `requirement = "<spec>"`, `registry = "<alias>"` |
| `local:…`, `git:…`, `docker:…` | unsupported | `scheme = "<local\|git\|docker>"` |

Rules:

- `project` and `system` are bare keywords — they take no `:` payload. `project:x`
  is invalid.
- For `pypi:` / `pypi+<alias>:`, everything after the first `:` is the
  `requirement` and is carried through verbatim (it is **not** PEP 508 /
  version-range validated in this story — that is resolution's concern). The
  `requirement` must be non-empty.
- An `<alias>` (the text between `pypi+` and `:`) must be non-empty and is
  matched as `[A-Za-z0-9_-]+`.
- `local:` / `git:` / `docker:` are recognized as *known but unsupported in
  FEAT-0002* and produce the unsupported kind (so the caller can give a
  "not yet supported" message rather than "unknown source").
- Anything else (empty after strip, an unrecognized `scheme:` prefix, a bare
  word other than `project`/`system`) is an **invalid spec**.

### Typed model shape (describe — do not implement)

A discriminated union over a `kind` literal, returned by `parse_source`.
Proposed as frozen pydantic models (consistent with the config models'
pydantic usage) or frozen dataclasses — the architect locks the choice:

- `PyPISource` — `kind: Literal["pypi"]`, `requirement: str`,
  `registry: str | None` (the `[sources]` alias, or `None` for the default
  registry).
- `ProjectSource` — `kind: Literal["project"]`.
- `SystemSource` — `kind: Literal["system"]`.
- `UnsupportedSource` — `kind: Literal["unsupported"]`, `scheme: str` (one of
  `local` / `git` / `docker`). Lets STY-0006+ light these up without changing
  the parser's contract.
- `ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource`
  — a `Literal`-discriminated `Annotated` union the resolver can `match` on.

Name note: the union is deliberately **not** called `SourceSpec` to avoid
colliding with the existing `gatecheck.config.SourceSpec` (the `[sources]`
table model).

### Error behavior

- `parse_source(spec: str)` raises a dedicated `SourceSpecError(ValueError)`
  (in `src/gatecheck/sources/`) for an invalid spec. It subclasses `ValueError`
  to stay consistent with `ConfigError`. Message format:
  `invalid source spec '<spec>': <reason>` (e.g.
  `invalid source spec 'pypi+:ruff': registry alias must not be empty`).
- The *unsupported but recognized* kinds (`local:`/`git:`/`docker:`) do **not**
  raise here — they return `UnsupportedSource` so the caller decides messaging.
- When the spec came from a loaded `check.toml`, the **config layer**, not the
  parser, is responsible for re-raising as `ConfigError` with
  `path:line:col: …` context — `parse_source` stays I/O- and location-free.
  This story wires that translation at the point where a `HookDef.from_` is
  parsed, reusing the existing `ConfigError(path, [(line, col, msg)])`
  constructor so diagnostics match the loader (`check.toml:LINE:COL:
  invalid source spec '…': …`). The mechanics of recovering `line:col` for a
  hook's `from` key follow the same approach STY-0002 used for schema errors.

## Tasks

- [ ] TSK-001: Create `src/gatecheck/sources/` package (`__init__.py` facade
  exporting `parse_source`, `ParsedSource`, the four kind models, and
  `SourceSpecError`; set `__all__`).
- [ ] TSK-002: Add the typed model module(s) — `PyPISource`, `ProjectSource`,
  `SystemSource`, `UnsupportedSource`, and the `ParsedSource` discriminated
  union (one class per file per core conventions).
- [ ] TSK-003: Add `SourceSpecError(ValueError)` in its own module.
- [ ] TSK-004: Implement `parse_source(spec: str) -> ParsedSource` with the
  parse-rule ordering and validation above.
- [ ] TSK-005: Wire `check.toml` → `ConfigError` translation: parse each
  `HookDef.from_` at load and re-raise `SourceSpecError` as `ConfigError`
  with `path:line:col` for the offending hook's `from` key.
- [ ] TSK-006: Write `tests/unit/test_source_parse.py` (≥ 15 unit tests
  covering every kind, every invalid-spec branch, and the unsupported kinds).
- [ ] TSK-007: Write `tests/integration/test_source_spec_acceptance.py`
  (4–6 tests asserting a bad `from` in a real `check.toml` yields a
  `ConfigError` matching `check.toml:\d+:\d+:`).
- [ ] TSK-008: Add a "Parsed source model" subsection to
  `docs/config/reference.md § Source spec syntax` documenting `parse_source`,
  the `ParsedSource` kinds, and the unsupported-vs-invalid distinction.

## Acceptance criteria

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
  subprocess (verifiable by inspection / mock-free test design).
- [ ] AC-10: `from gatecheck.sources import parse_source, ParsedSource,
  SourceSpecError` works.
- [ ] AC-11: `mypy --strict src/gatecheck/sources/` passes with no new errors.
- [ ] AC-12: No new runtime dependencies added.

## Notes

- Keep `parse_source` synchronous and pure; resolution (STY-0005) and network
  (STY-0006) are deliberately absent.
- The `requirement` string is **not** PEP 508-validated here — version-range
  parsing is resolution's concern. Carry it through verbatim.
- `UnsupportedSource` exists so STY-0006+ can add `local`/`git`/`docker`
  without breaking `parse_source`'s contract (Open/Closed).
- Naming collision to watch: `gatecheck.config.SourceSpec` is the `[sources]`
  *table* model; the parsed-spec union is `ParsedSource` in the new
  `gatecheck.sources` package. Do not conflate them.
- Architect to lock: pydantic models vs frozen dataclasses for the union, and
  the exact `line:col` recovery for a hook's `from` key (mirror STY-0002).
- Pre-existing inconsistency flagged for the architect (out of STY-0004 scope):
  `src/gatecheck/env/manager.py` imports `gatecheck.config.schema`, a module
  that does not exist in the current `config/` package.
