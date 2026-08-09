---
id: BUILD-0001-ARCH
title: Architecture sketch for STY-0001 (Config Loader)
parent: BUILD-0001
target_story: STY-0001
status: Locked
date: 2026-05-28
---

# BUILD-0001-ARCH: Architecture sketch for STY-0001

> **LOCKED CONTRACT.** Lanes B (ATDD), C (TDD), and D (implementation) all
> consume this document. Any change requires re-opening BUILD-0001 §1.2.

---

## 1. Module layout

One concern per file. Filenames follow `snake_case(ClassName)` per
`python.md`. The bundled `schema.py` stub is removed (BUILD-0001 G-4 / C4).

| File | Single responsibility |
|---|---|
| `src/hooksmith/config/source_spec.py` | Defines `class SourceSpec` only. |
| `src/hooksmith/config/hook_def.py` | Defines `class HookDef` only. |
| `src/hooksmith/config/group_def.py` | Defines `class GroupDef` only. |
| `src/hooksmith/config/hooksmith_config.py` | Defines `class HooksmithConfig` only. |
| `src/hooksmith/config/loader.py` | Defines `load_config(path: Path) -> HooksmithConfig` only. |
| `src/hooksmith/config/__init__.py` | **Public facade.** Re-exports the five symbols below. Documented exception to python.md no-import-forwarding rule (BUILD-0001 G-3 / C3). |
| `src/hooksmith/config/schema.py` | **TO BE DELETED.** No back-compat re-export. |

---

## 2. Public API surface

Exactly five symbols are exported from `hooksmith.config`. `__all__` MUST
list them in this order:

```python
__all__ = ["HooksmithConfig", "GroupDef", "HookDef", "SourceSpec", "load_config"]
```

| Symbol | Kind | Imported from |
|---|---|---|
| `load_config` | function | `hooksmith.config.loader` |
| `HooksmithConfig` | pydantic model | `hooksmith.config.hooksmith_config` |
| `HookDef` | pydantic model | `hooksmith.config.hook_def` |
| `SourceSpec` | pydantic model | `hooksmith.config.source_spec` |
| `GroupDef` | pydantic model | `hooksmith.config.group_def` |

No other symbol is part of the STY-0001 public surface. Internal helpers
(if any) MUST be prefixed `_` and excluded from `__all__`.

---

## 3. Schema specification

Field set is the intersection of the keys present in `check.toml` (repo
root) and `tests/fixtures/check.toml.sample`. Richer keys documented in
`docs/config/reference.md` (e.g. `name`, `exclude`, `max-workers`,
`extra-registries`, `[workspace]`, `[package]`, additional `when` keys)
are **out of scope** — §8.

All four models inherit `pydantic.BaseModel`. Every model sets
`model_config = ConfigDict(extra="forbid", populate_by_name=True)`. See §6
and §7.

### 3.1 `SourceSpec` — `[sources]` table

| Python name | TOML alias | Type | Default | Validation |
|---|---|---|---|---|
| `default_registry` | `default-registry` | `str \| None` | `None` | If present, must be non-empty string. No URL parsing in STY-0001. |

### 3.2 `HookDef` — `[[hook]]` table entry

| Python name | TOML alias | Type | Default | Validation |
|---|---|---|---|---|
| `id` | `id` | `str` | **required** | Non-empty. |
| `from_` | `from` | `str` | **required** | Non-empty. Aliased because `from` is a Python keyword. |
| `run` | `run` | `str` | **required** | Non-empty. |
| `files` | `files` | `str \| None` | `None` | Optional glob pattern. No glob compilation in STY-0001. |
| `pass_files` | `pass-files` | `bool` | `True` | — |
| `depends_on` | `depends-on` | `list[str]` | `[]` (via `Field(default_factory=list)`) | Each entry non-empty. Referential validity (hook ids exist) is NOT checked here — that's a later story. |
| `when` | `when` | `HookWhen \| None` | `None` | Inline-table; see 3.2.1. |

#### 3.2.1 `HookWhen` — nested inline-table model (defined inside `hook_def.py`)

Scoped to the keys actually used in the repo's `check.toml`. All other
`when` keys from the docs are out of scope for STY-0001 (§8).

| Python name | TOML alias | Type | Default | Validation |
|---|---|---|---|---|
| `env_not` | `env-not` | `str \| None` | `None` | Env-var name. |
| `on_ci` | `on-ci` | `bool \| None` | `None` | Tri-state: unset / true / false. |

Same `model_config` (`extra="forbid"`, `populate_by_name=True`).

### 3.3 `GroupDef` — `[group.<name>]` table

| Python name | TOML alias | Type | Default | Validation |
|---|---|---|---|---|
| `hooks` | `hooks` | `list[str]` | **required** | Must be non-empty list of non-empty strings. Referential validity NOT checked here. |
| `parallel` | `parallel` | `bool` | `False` | — |
| `fail_fast` | `fail-fast` | `bool` | `False` | — |
| `on_event` | `on-event` | `Literal["commit", "push"] \| None` | `None` | Restricted to the two event names exercised by the repo's `check.toml`. Other docs values (`commit-msg`, `merge`) are out of scope (§8). |

### 3.4 `HooksmithConfig` — top-level document

| Python name | TOML alias | Type | Default | Validation |
|---|---|---|---|---|
| `hook` | `hook` | `list[HookDef]` | `[]` (via `Field(default_factory=list)`) | Pydantic recursively validates each entry. Hook-id uniqueness NOT enforced here (later story). |
| `group` | `group` | `dict[str, GroupDef]` | `{}` (via `Field(default_factory=dict)`) | Keys are arbitrary group names. |
| `sources` | `sources` | `SourceSpec \| None` | `None` | Absent `[sources]` table yields `None`. |

No field is aliased at the top level; TOML names already match.

---

## 4. Function signatures

```python
# src/hooksmith/config/loader.py
from pathlib import Path
from hooksmith.config.hooksmith_config import HooksmithConfig

def load_config(path: Path) -> HooksmithConfig: ...
```

Semantics:

- **Synchronous.** No `async`. (STY-0001 Notes: "Keep `load_config`
  synchronous and side-effect-free.")
- **Side-effect-free** beyond opening `path` in binary mode for `tomllib`.
  No writes, no globals mutated, no logging at import time.
- **No `Path` coercion.** Caller MUST pass `pathlib.Path`. Strings are
  rejected by the type checker; runtime behaviour with a `str` is
  undefined for STY-0001.
- Implementation outline (informative, not normative):
  `tomllib.load(open(path, "rb"))` → `HooksmithConfig.model_validate(...)`.

---

## 5. Error behavior

`load_config` does **NOT** wrap or translate exceptions in STY-0001.
Errors propagate as-is for the caller to handle. STY-0002 owns
file:line:col translation of `ValidationError`.

| Condition | Exception raised | Source |
|---|---|---|
| `path` does not exist | `FileNotFoundError` | `open()` call inside `tomllib.load`. |
| `path` exists but is not readable | `PermissionError` | `open()`. |
| File contents are not valid TOML | `tomllib.TOMLDecodeError` | `tomllib.load`. |
| TOML parses but violates the schema (missing required field, wrong type, unknown key, bad `Literal` value) | `pydantic.ValidationError` | `HooksmithConfig.model_validate`. |
| Any of the four above | wrapped as `ConfigError` (a `ValueError` subclass) in `load_config`, with the original exception preserved on `__cause__` | STY-0002 (BUILD-0002 / [BUILD-0002-ARCH](0002-architecture-decision.md) §5) |

**Explicitly out of scope** for STY-0001:

- No custom exception type (e.g. `ConfigError`) is introduced.
- No conversion of `ValidationError` to file:line:col — STY-0002.
- No logging, no `warnings.warn`. Unknown keys raise via `extra="forbid"`.

**STY-0002 update.** As of BUILD-0002, `load_config` now wraps every
exception in §5's table as `ConfigError(ValueError)`. The two-layer test
strategy (BUILD-0002 §6) means `__cause__` is asserted alongside
`isinstance(exc, ConfigError)` in all STY-0001 tests so the underlying
exception identity remains a hard contract. See
[BUILD-0002-ARCH](0002-architecture-decision.md).

---

## 6. Pydantic v2 config knobs

Every model in §3 uses **exactly** this configuration:

```python
model_config = ConfigDict(
    extra="forbid",
    populate_by_name=True,
)
```

**Justification.**

- `extra="forbid"` — STY-0001 TSK-004 mandates "unknown key warns or
  fails per pydantic config". Failing loudly is preferred over silent
  drop: a typo in `pass-fiels` would otherwise become a silent default
  `True`, masking config bugs. The acceptance test fixture explicitly
  exercises unknown-key rejection.
- `populate_by_name=True` — required so both TOML (`pass-files`) and
  Python-native (`pass_files`) names construct models. See §7.
- No `frozen=True` — immutability is not in the acceptance criteria and
  may be added later without breaking the contract.
- No `str_strip_whitespace`. TOML strings are taken verbatim.

**Accepted deviation (post-implementation, BUILD-0001 Lane F1 SHOULD_FIX
S1):** every boolean field in §3 (`HookDef.pass_files`, `HookWhen.on_ci`,
`GroupDef.parallel`, `GroupDef.fail_fast`) is typed as `pydantic.StrictBool`
rather than plain `bool`. `model_config` itself is unchanged. Reason:
pydantic v2's lax mode coerces strings like `"yes"` to `True`, but
`test_load_config_raises_validation_error_on_wrong_type` requires
`parallel = "yes"` to raise `ValidationError`. Per-field `StrictBool` is
the minimum change that satisfies the test without enabling
model-wide `strict=True` (which would tighten string parsing in ways the
TOML loader doesn't want). Future stories may revisit if a `strict=True`
model-wide policy becomes preferable.

---

## 7. Naming for hyphenated TOML keys

TOML idiomatic keys use hyphens; Python identifiers cannot. Resolution:
**every hyphenated key uses `Field(alias="<toml-name>")`** and every
model sets `populate_by_name=True` (see §6). Both names work at
construction time — TOML loading uses the alias path; tests and Python
callers may use either.

| Model | Python attr | TOML alias |
|---|---|---|
| `SourceSpec` | `default_registry` | `default-registry` |
| `HookDef` | `pass_files` | `pass-files` |
| `HookDef` | `depends_on` | `depends-on` |
| `HookDef` | `from_` | `from` (Python keyword; same alias mechanism) |
| `HookWhen` | `env_not` | `env-not` |
| `HookWhen` | `on_ci` | `on-ci` |
| `GroupDef` | `fail_fast` | `fail-fast` |
| `GroupDef` | `on_event` | `on-event` |

Fields whose TOML and Python names already match (`id`, `run`, `files`,
`when`, `hooks`, `parallel`, `hook`, `group`, `sources`) do **not** use
`Field(alias=...)`.

Tests in Lane C MUST exercise both name forms for at least one
hyphenated field per model, to lock the alias scheme in place.

---

## 8. Out of scope for STY-0001

The following appear in `docs/config/reference.md` or in adjacent
features but are **deliberately not modelled** by this story. The schema
will reject them (`extra="forbid"`), which is the correct behaviour for
the locked STY-0001 surface. They will be added by their owning
follow-up stories:

- `HookDef`: `name`, `exclude`, `fail-fast`, `packages` (workspace-only).
- `HookWhen`: `branch`, `branch-not`, `branch-matches`, `files-match`, `env`.
- `GroupDef`: `max-workers`; `on-event` values `"commit-msg"` and `"merge"`.
- `SourceSpec`: `extra-registries`.
- Top-level `[workspace]` and `[package]` tables (monorepo / inheritance).
- Hook-id uniqueness enforcement and `depends-on` referential checks.
- `from` string parsing into a structured source spec
  (`pypi:`, `git:`, `docker:`, etc.).
- Error-position reporting (file:line:col) — STY-0002.
- Config file lookup / upward search — separate story.
- `pyproject.toml` `[tool.hooksmith]` ingestion — separate story.
- Async I/O — explicitly disallowed by STY-0001 Notes.
- Any import of `hooksmith_core` from this package — forbidden by
  STY-0001 acceptance criterion 4.

---

## Appendix — Cross-references

- Story: `planning/features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md`
- Build plan: `planning/build-plans/0001-multiagent-build-sty-0001.md` (§1.2 C3, C4; §9 G-3, G-4, G-8)
- ADR: `planning/adr/0001-python-host-rust-core.md`
- Docs reference: `docs/config/reference.md`
- Sample fixture: `tests/fixtures/check.toml.sample`
- Real-world fixture (acceptance witness): `check.toml` (repo root)
