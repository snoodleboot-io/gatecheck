---
id: BUILD-0004-ARCH
title: Architecture decision for STY-0004 (parse + classify source specs)
parent: BUILD-0004
target_story: STY-0004
status: Locked
date: 2026-06-28
---

# BUILD-0004-ARCH: Parse & classify a hook's source spec

> **LOCKED CONTRACT.** The code / test / review lanes consume this document.
> Any change requires re-opening BUILD-0004 §1.

---

## §1 Model representation — **frozen pydantic models** (LOCKED)

### Decision

The four kind models (`PyPISource`, `ProjectSource`, `SystemSource`,
`UnsupportedSource`) are **frozen pydantic `BaseModel`s** —
`model_config = ConfigDict(frozen=True, extra="forbid")` — each with a
`kind: Literal[...]` discriminator field. The `ParsedSource` public type is a
**plain `typing.Union`** alias of the four; an internal
`Annotated[Union[...], Field(discriminator="kind")]` + `TypeAdapter` is used
only inside `parser.py` for construction/validation.

### Justification (vs frozen dataclasses)

1. **Consistency with the existing config models.** Every model in
   `gatecheck.config` (`SourceSpec`, `HookDef`, `HookWhen`, `GroupDef`,
   `GatecheckConfig`) is a pydantic `BaseModel` with `ConfigDict`. The story
   explicitly prefers "consistent with the config models' pydantic usage."
   Using dataclasses here would introduce a second modelling idiom in the same
   codebase for no benefit.

2. **Validation comes for free.** `requirement` non-empty and `scheme ∈
   {local, git, docker}` can be expressed as `min_length=1` /
   `Literal[...]` constraints, and equality/`repr` (needed by AC-2/AC-3 tests)
   are provided. We still keep authoritative validation in `parse_source`
   (so messages match the required format), but the model layer is a backstop.

3. **`frozen=True` gives hashable, immutable values** — appropriate for a value
   object the resolver passes around and may key on. Dataclasses would need
   `@dataclass(frozen=True)`; pydantic's `frozen` is equivalent and idiomatic
   here.

### Discriminator mechanism (exact)

- Each model declares `kind: Literal["pypi" | "project" | "system" |
  "unsupported"]` with a **default** equal to its literal, so callers and tests
  may construct `PyPISource(requirement=..., registry=...)` without passing
  `kind` (AC-2/AC-3 construct without `kind`).
- **Public `ParsedSource`** (in `parsed_source.py`) is a **plain union** so
  structural `match` narrows cleanly under `mypy --strict`:

  ```python
  ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource
  ```

  This makes AC-7 work directly:

  ```python
  match parse_source(spec):
      case PyPISource(requirement=r, registry=reg): ...
      case ProjectSource(): ...
      case SystemSource(): ...
      case UnsupportedSource(scheme=s): ...
  ```

- The parser does **not** need pydantic's discriminated `TypeAdapter` to do its
  job — it constructs the concrete model directly after string matching. The
  `Annotated[..., Field(discriminator="kind")]` form is documented here as the
  *canonical serialization shape* for any future code that needs to validate a
  `ParsedSource` from a dict (e.g. caching), but **STY-0004 does not build a
  TypeAdapter** unless a lane finds it necessary; the plain union alias is the
  locked public contract.

---

## §2 Module layout — `src/gatecheck/sources/`

One class per file (core conventions: filename = snake_case of the class).

| File | Single responsibility |
|---|---|
| `src/gatecheck/sources/pypi_source.py` | `PyPISource` frozen pydantic model. |
| `src/gatecheck/sources/project_source.py` | `ProjectSource` frozen pydantic model. |
| `src/gatecheck/sources/system_source.py` | `SystemSource` frozen pydantic model. |
| `src/gatecheck/sources/unsupported_source.py` | `UnsupportedSource` frozen pydantic model. |
| `src/gatecheck/sources/parsed_source.py` | `ParsedSource` union type alias (no class). |
| `src/gatecheck/sources/source_spec_error.py` | `SourceSpecError(ValueError)`. |
| `src/gatecheck/sources/parser.py` | `parse_source(spec) -> ParsedSource` + private helpers. No class. |
| `src/gatecheck/sources/__init__.py` | Facade; imports + `__all__`. |

### `__init__.py` exports / `__all__`

Alphabetical (uppercase before lowercase, matching BUILD-0001..0003 §:

```python
"""Public facade for gatecheck.sources (BUILD-0004-ARCH §2)."""
from __future__ import annotations

from gatecheck.sources.parsed_source import ParsedSource
from gatecheck.sources.parser import parse_source
from gatecheck.sources.project_source import ProjectSource
from gatecheck.sources.pypi_source import PyPISource
from gatecheck.sources.source_spec_error import SourceSpecError
from gatecheck.sources.system_source import SystemSource
from gatecheck.sources.unsupported_source import UnsupportedSource

__all__ = [
    "ParsedSource",
    "ProjectSource",
    "PyPISource",
    "SourceSpecError",
    "SystemSource",
    "UnsupportedSource",
    "parse_source",
]
```

---

## §3 Model specs (exact types)

```python
# pypi_source.py
class PyPISource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["pypi"] = "pypi"
    requirement: str = Field(min_length=1)
    registry: str | None = None

# project_source.py
class ProjectSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["project"] = "project"

# system_source.py
class SystemSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["system"] = "system"

# unsupported_source.py
class UnsupportedSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["unsupported"] = "unsupported"
    scheme: Literal["local", "git", "docker"]

# parsed_source.py
ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource
```

Notes:
- `requirement` carries the spec **verbatim** — NOT PEP 508 validated (story
  §Notes). `min_length=1` is the only constraint; emptiness is also caught
  earlier in `parse_source` so the user-facing message is the spec'd one.
- `registry` is the `[sources]` alias name or `None` for the default registry —
  it is **not** resolved against `[sources]` here (that is STY-0006).

---

## §4 `parse_source` algorithm & error message table

```python
# parser.py
def parse_source(spec: str) -> ParsedSource: ...
```

### Control flow (match order = story's first-rule-wins order)

`raw = spec` (kept for the error message); `s = spec.strip()`.

1. **`s == ""`** → invalid (empty).
2. **`s == "project"`** → `ProjectSource()`.
3. **`s == "system"`** → `SystemSource()`.
4. **`s` starts with `"pypi+"`** → split on the **first** `:`.
   - If no `:` present → invalid (malformed pypi spec).
   - `alias = s[len("pypi+"):colon]`, `req = s[colon+1:]`.
   - If `alias == ""` → invalid (empty alias).
   - If `alias` does not fully match `[A-Za-z0-9_-]+` → invalid (bad alias).
   - If `req == ""` → invalid (empty requirement).
   - else → `PyPISource(requirement=req, registry=alias)`.
5. **`s` starts with `"pypi:"`** → `req = s[len("pypi:"):]`.
   - If `req == ""` → invalid (empty requirement).
   - else → `PyPISource(requirement=req, registry=None)`.
6. **`s` starts with `"local:"` / `"git:"` / `"docker:"`** →
   `UnsupportedSource(scheme=<scheme>)`. (Does **not** raise. Payload after `:`
   is ignored at this stage — recognizing the scheme is enough; STY-0006 will
   parse the payload.)
7. **`s` matches `^[A-Za-z0-9_+-]+:`** (any other `scheme:` prefix) → invalid
   (unknown scheme).
8. **otherwise** (a bare word like `ruff`, or `project:x`/`system:x` which fall
   through here because they are not exact keywords and have no recognized
   scheme prefix) → invalid (unrecognized spec).

> `project:x` is rejected: step 2 requires an exact match (`==`), so `project:x`
> falls through. It is **not** a recognized `scheme:` for step 6/7's allow-list,
> and `project` is not in the known-scheme set, so it lands in step 7 (a
> `scheme:`-shaped string with an unknown scheme) → invalid. Same for
> `system:x`. This satisfies "`project:x` is invalid."

### Error construction

Every invalid branch raises:

```python
raise SourceSpecError(spec, reason)
```

where `SourceSpecError.__init__(spec, reason)` renders the message
`invalid source spec '{spec}': {reason}` using the **original** `spec`
(un-stripped, so the user sees exactly what they wrote).

### Message table (exact `reason` strings — LOCKED)

| Branch | Example input | `reason` | Full message |
|---|---|---|---|
| empty / whitespace | `""`, `"   "` | `spec is empty` | `invalid source spec '': spec is empty` |
| pypi+ no colon | `"pypi+internal"` | `expected 'pypi+<alias>:<requirement>'` | `invalid source spec 'pypi+internal': expected 'pypi+<alias>:<requirement>'` |
| empty alias | `"pypi+:ruff"` | `registry alias must not be empty` | `invalid source spec 'pypi+:ruff': registry alias must not be empty` |
| bad alias chars | `"pypi+a b:ruff"` | `registry alias must match [A-Za-z0-9_-]+` | `invalid source spec 'pypi+a b:ruff': registry alias must match [A-Za-z0-9_-]+` |
| empty requirement (pypi+) | `"pypi+internal:"` | `requirement must not be empty` | `invalid source spec 'pypi+internal:': requirement must not be empty` |
| empty requirement (pypi) | `"pypi:"` | `requirement must not be empty` | `invalid source spec 'pypi:': requirement must not be empty` |
| unknown scheme | `"bogus:thing"`, `"project:x"`, `"system:x"` | `unknown source scheme '<scheme>'` | `invalid source spec 'bogus:thing': unknown source scheme 'bogus'` |
| bare word | `"ruff"` | `expected one of: project, system, pypi:<req>, pypi+<alias>:<req>` | `invalid source spec 'ruff': expected one of: project, system, pypi:<req>, pypi+<alias>:<req>` |

The unsupported (recognized) schemes `local:` / `git:` / `docker:` **never**
appear in this table — they return `UnsupportedSource` (AC-4).

### Purity (AC-9)

`parse_source` imports only `re` and the four models + error. It touches no
filesystem, network, env, or subprocess. Verifiable by inspection; tests need
no mocks.

---

## §5 `SourceSpecError`

```python
# source_spec_error.py
class SourceSpecError(ValueError):
    """Raised by parse_source for a syntactically invalid `from` spec."""
    spec: str
    reason: str

    def __init__(self, spec: str, reason: str) -> None:
        self.spec = spec
        self.reason = reason
        super().__init__(f"invalid source spec '{spec}': {reason}")
```

- Base class `ValueError` — consistent with `ConfigError(ValueError)` (AC-6).
- Carries structured `spec` + `reason` so the config layer can re-format
  without string-scraping.
- Location-free and I/O-free: it knows nothing about files or line/col.

---

## §6 check.toml → ConfigError translation (TSK-005) — LOCKED integration point

### Where: `load_config` in `src/gatecheck/config/loader.py`, **eager**

After `GatecheckConfig.model_validate(data)` succeeds, `load_config` iterates
the validated hooks and parses each `from_` **eagerly** (during `load_config`),
before returning. A new private helper in `_error_translator.py`,
`_locate_source_spec_errors(...)`, recovers `(line, col, msg)` for any failing
`from`, and `load_config` raises `ConfigError(path, errors)` exactly as it does
for `pydantic.ValidationError`.

### Justification — eager (not lazy)

- **AC-8 requires** a bad `from` to surface as `ConfigError` with
  `check.toml:LINE:COL:` from `load_config`. Lazy parsing (at resolve time)
  could not produce a `ConfigError` with file context because the resolver no
  longer has the TOML source/positions.
- **Single diagnostic surface.** STY-0002 made `load_config` the one place that
  emits `path:line:col:` errors. Eager parse keeps that invariant: all config
  diagnostics come out of `load_config`.
- **Cost is negligible** — parsing is pure string work over a handful of hooks.
- `parse_source` itself stays I/O- and location-free; only the *translation*
  lives in the config layer (story §Error behavior).

### `line:col` recovery (mirrors STY-0002's `_locate_validation_errors`)

`load_config` must re-`tomlkit.parse(source)` (it already does this in the
ValidationError branch) and pass the source + doc into the new helper:

```python
# loader.py (additions, after successful model_validate)
config = GatecheckConfig.model_validate(data)
spec_errors = _locate_source_spec_errors(config, source)
if spec_errors:
    raise ConfigError(path, spec_errors)
return config
```

```python
# _error_translator.py (new helper)
def _locate_source_spec_errors(
    config: GatecheckConfig,
    source: str,
) -> list[tuple[int, int, str]]:
    """For each hook whose `from_` fails parse_source, return (line, col, msg)
    anchored at that hook's `from` key in `source`."""
    results: list[tuple[int, int, str]] = []
    for index, hook in enumerate(config.hook):
        try:
            parse_source(hook.from_)
        except SourceSpecError as exc:
            anchor = _nth_aot_header_line(source, "hook", index)          # reused
            pos = _scan_field(source, anchor, "from", hook.from_)          # reused
            line, col = pos if pos is not None else (anchor, 1)
            msg = f"{exc} (hook: {hook.id})"
            results.append((line, col, msg))
    return results
```

Mechanism reuse (NO re-implementation):
- **`_nth_aot_header_line(source, "hook", index)`** — already in
  `_error_translator.py`; returns the 1-based line of the Nth `[[hook]]`
  header. The validated `config.hook` list preserves source order, so the list
  index is the AoT index.
- **`_scan_field(source, anchor_line, "from", target_text=hook.from_)`** —
  already in `_error_translator.py`; forward-scans for `from =` from the header
  line, stops at the next table header, and uses `hook.from_` as the
  verification needle (the field's RHS contains the spec text) to disambiguate.
  Returns `(line, col)` (col = 1-based start of `from`).
- Fallback to `(anchor, 1)` if the scan fails (e.g. dotted/inline edge cases),
  identical to STY-0002's parent-anchor fallback.

This produces, for `from = "bogus:thing"` on the 2nd hook at line 9:

```
check.toml:9:1: invalid source spec 'bogus:thing': unknown source scheme 'bogus' (hook: lint)
```

which satisfies AC-8 (`^check\.toml:\d+:\d+:` and names the bad spec; `(hook:
…)` names the offending hook per FEAT-0002 acceptance).

### Multiple bad specs

All failing hooks are collected and surfaced together (one `(line, col, msg)`
per bad hook), matching STY-0002's multi-error behavior. `UnsupportedSource`
results are valid — they do **not** add an error (a `local:`/`git:`/`docker:`
`from` loads cleanly; the "not yet supported" message is the resolver's job in
a later story).

### Import direction

`config/_error_translator.py` and `config/loader.py` import from
`gatecheck.sources` (`parse_source`, `SourceSpecError`). `gatecheck.sources`
imports **nothing** from `gatecheck.config`. No circular import: `sources` is a
leaf package; `config` depends on it one-directionally.

---

## §7 Public API surface (LOCKED)

```python
from gatecheck.sources import (
    parse_source,
    ParsedSource,
    SourceSpecError,
    PyPISource,
    ProjectSource,
    SystemSource,
    UnsupportedSource,
)
```

`gatecheck.config`'s public surface is **unchanged** — no new symbol is
exported from `gatecheck.config`. In particular, `SourceSpec` (the `[sources]`
table model) is untouched and is **not** re-exported from `gatecheck.sources`.
The TSK-005 wiring is internal to `loader.py` / `_error_translator.py` and adds
no new public config symbol.

---

## §8 mypy --strict cleanliness

- `from __future__ import annotations` in every new module.
- Every function fully annotated; `parse_source(spec: str) -> ParsedSource`.
- `ParsedSource` is a plain union → `match`/`case PyPISource()` narrows under
  strict (AC-7, AC-11).
- pydantic `Literal[...]` discriminator fields are statically typed; no `Any`
  leaks.
- Helper return types explicit: `_locate_source_spec_errors(...) ->
  list[tuple[int, int, str]]`.
- No `# type: ignore` introduced in the new package.
- `re` patterns are module-level compiled constants (`_ALIAS_RE`,
  `_SCHEME_RE`) typed as `re.Pattern[str]`.

## §9 pydantic knobs

- `ConfigDict(frozen=True, extra="forbid")` on all four models.
- `kind` fields carry a default equal to their literal (construct without
  `kind`).
- `requirement: str = Field(min_length=1)`; `registry: str | None = None`;
  `scheme: Literal["local", "git", "docker"]`.
- No validators needed — string-shape validation lives authoritatively in
  `parse_source` so the user-facing message matches §4's table.

---

## §10 Baseline issues — recommendations (user decides; do not implement here)

1. **`env/manager.py:13` → `from gatecheck.config.schema import HookDef`** —
   broken import; `config/schema.py` does not exist (real module:
   `config/hook_def.py`). Only this one line references it (`grep` confirms the
   sole `config.schema` import; the `test_config_schema.py` string in
   `tests/integration/test_config_load_acceptance.py:165` is a filename
   literal, not an import). Fails `mypy --strict` today.
   **Recommendation: FIX IN BUILD-0004** — one-line change to
   `from gatecheck.config.hook_def import HookDef`. It is the direct downstream
   consumer of FEAT-0002 (STY-0005 will call `parse_source` here), it is broken
   now, and a clean `mypy --strict` gate for this build is easier if this is
   green. Smallest possible change; no behavior touched.

2. **`core.py:11` — `# type: ignore[import-not-found]` on `gatecheck_core`** —
   the Rust-extension import. **Recommendation: OUT of scope (defer).** It is
   unrelated to source-spec parsing, lives on the Python↔Rust boundary
   (ADR-0001) that STY-0004 deliberately avoids, and STY-0004 is a pure-Python
   slice with no dependency on the Rust core (FEAT-0002 acceptance). Fold it
   into a future runner/core story.

---

## §11 Explicitly OUT of scope (re-stated)

- Resolving `project`/`system` to executables (STY-0005).
- PyPI/private network resolution + venv creation (STY-0006 / Environments).
- PEP 508 / version-range validation of `requirement`.
- Parsing the payload of `local:`/`git:`/`docker:` beyond the scheme name.
- Cache key / hit-miss explainability.
- Any new public symbol on `gatecheck.config`.
- New runtime dependencies.

---

## Appendix

- Story:
  `planning/features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md`
- Feature: `planning/features/FEAT-0002-source-resolution/feature.md`
- Build charter: `planning/build-plans/0004-charter.md`
- Predecessor architecture documents:
  - `0001-architecture-sketch.md` — schema + `load_config` contract.
  - `0002-architecture-decision.md` — `ConfigError` + error-wrapping (§2, §3).
  - `0003-architecture-decision.md` — dumper; `__all__` ordering convention.
- Reused machinery (STY-0002): `src/gatecheck/config/_error_translator.py`
  (`_nth_aot_header_line`, `_scan_field`, parent-anchor fallback);
  `src/gatecheck/config/config_error.py` (`ConfigError(path, [(line, col,
  msg)])`).
- Existing collision to avoid: `src/gatecheck/config/source_spec.py`
  (`SourceSpec` = `[sources]` table model).
- Unit tests (red): `tests/unit/test_source_parse.py`.
- Acceptance tests (red): `tests/integration/test_source_spec_acceptance.py`.
