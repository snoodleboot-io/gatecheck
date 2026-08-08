---
id: BUILD-0003-ARCH
title: Architecture decision for STY-0003 (round-trip config dump)
parent: BUILD-0003
target_story: STY-0003
status: Locked
date: 2026-05-29
---

# BUILD-0003-ARCH: Round-trip config dump

> **LOCKED CONTRACT.** Lanes B, C, D consume this document. Any change
> requires re-opening BUILD-0003 §1.2.

---

## §1 Strategy choice — **Option A (model_dump + dict walk)**

### Decision

Use **Option A**: call `config.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)` to obtain a plain Python dict, then walk that dict to build a `tomlkit` document.

### Justification

**Option A is preferred** over Option B (direct pydantic field walk) for three reasons:

1. **Alias resolution is delegated to pydantic, not duplicated.** Every
   hyphenated alias (`from`, `pass-files`, `depends-on`, `env-not`, `on-ci`,
   `fail-fast`, `on-event`, `default-registry`) is already declared on each
   model's `Field(alias=...)`. With `by_alias=True`, pydantic emits the
   correct TOML key names automatically. Option B would require the dumper to
   re-enumerate every alias — a second source of truth that diverges when a
   new field is added.

2. **Default and None suppression is delegated to pydantic, not hand-coded.**
   `exclude_none=True` and `exclude_defaults=True` let pydantic apply its own
   field-level knowledge of what is absent or at its default. Option B would
   need to compare each value against its `Field.default` or
   `Field.default_factory`, which is fragile (equality semantics differ for
   lists vs scalars) and must be updated for every new field.

3. **Scope of the dumper narrows to TOML construction only.** After
   `model_dump` runs, the dict already has the right keys and omitted the
   right fields. The walker's only job is to map Python dict structure to the
   correct tomlkit node types — a single concern per §6.

### `exclude_defaults=True` vs `exclude_unset=True`

**Use `exclude_defaults=True`.** Here is why:

- `exclude_unset=True` omits fields that were *not explicitly provided* to the
  constructor. A `HooksmithConfig` produced by `model_validate(data)` inside
  `load_config` has **all** fields set — pydantic considers every field
  "explicitly provided" even when the input data simply lacked the key and
  pydantic filled in the default. On such an object, `exclude_unset=True`
  would include every field that appeared in the TOML source regardless of
  whether its value equals the default, and would still omit fields that were
  absent from the source. This is the *correct* behavior for preserving user
  intent from a hand-written file — but `dump_config` must also work when
  called on a programmatically constructed `HooksmithConfig()` (e.g. in
  tests), where nothing is "set."
- `exclude_defaults=True` omits fields whose current value equals the field's
  declared default (regardless of how the object was constructed). For a
  round-trip dumper whose purpose is to produce a clean, minimal config file,
  this is exactly right: if `pass_files=True` (the default), there is no
  reason to write `pass-files = true`; omitting it produces the same
  round-trip result.

**Implication for AC-7:** the tests in `test_config_dumper.py` explicitly
assert that `pass-files = true` is absent when a hook was constructed with
`"pass-files": True` (the default) and present when constructed with
`"pass-files": False` (non-default). `exclude_defaults=True` satisfies both
assertions correctly.

**One edge case — `depends_on=[]`.** The default for `depends_on` is
`Field(default_factory=list)`. Pydantic v2 compares the current list value
against `[]` for `exclude_defaults=True`, so an empty list is excluded. Tests
assert `depends-on` is absent from a hook with `depends_on=[]`. This works
correctly.

---

## §2 `dump_config` function signature and contract

```python
# src/hooksmith/config/dumper.py
from pathlib import Path
from hooksmith.config.hooksmith_config import HooksmithConfig

def dump_config(config: HooksmithConfig, path: Path) -> None: ...
```

### Contract

- **Synchronous.** No `async`.
- **Side-effect-free** beyond writing `path`. No globals mutated, no logging,
  no temp files.
- **Raises `IsADirectoryError`** (a subclass of `OSError`) if `path` is an
  existing directory. This is raised naturally by `path.write_text(...)` on
  Linux when `path` is a directory — no explicit pre-check is needed. The
  test suite accepts either `IsADirectoryError` or `OSError`:
  ```python
  pytest.raises((IsADirectoryError, OSError))
  ```
- **`FileNotFoundError`** propagates unchanged if `path`'s parent directory
  does not exist. No parent-creation logic is in scope.
- **`PermissionError`** propagates unchanged if `path` is not writable.
- No new exception types are introduced by `dump_config` beyond what the OS
  and `tomlkit` already raise.
- No `Path` coercion: caller MUST pass `pathlib.Path`.

---

## §3 TOML construction algorithm

All construction uses `tomlkit` document-building primitives. The raw dict
produced by `model_dump` (see §1) is the input to the walker.

### Top-level document

```python
doc = tomlkit.document()
```

Sections are added in the following order to match the canonical `check.toml`
layout: `[sources]`, `[[hook]]`, `[group.<name>]`. Sections whose backing
data is absent (empty list, empty dict, `None`) are **not added** to the
document.

### `[sources]` — simple table

The `sources` key in the top-level dict is present only when
`config.sources is not None` (the `exclude_none=True` pass eliminates it
otherwise). When present, its value is a dict with at most one key
(`default-registry`).

```python
# sources_data is already a dict from model_dump (may be absent or empty)
src_table = tomlkit.table()
for key, value in sources_data.items():
    src_table.add(key, value)
doc.add("sources", src_table)
```

The resulting TOML is:
```toml
[sources]
default-registry = "https://pypi.org/simple"
```

### `[[hook]]` — TOML array-of-tables

Each entry in the `hook` list is emitted as a separate `[[hook]]` block. The
`when` sub-dict (if present) is built as a `tomlkit.inline_table()` before
being added to the hook table (see `when` subsection below).

```python
hooks_aot = tomlkit.aot()
for hook_data in hook_list:   # each hook_data is a dict from model_dump
    t = tomlkit.table()
    for key, value in hook_data.items():
        if key == "when":
            t.add("when", _build_inline_table(value))
        else:
            t.add(key, value)
    hooks_aot.append(t)
doc.add("hook", hooks_aot)
```

Fields omitted by `model_dump` (e.g. `pass-files` when `True`, `depends-on`
when `[]`, `files` when `None`, `when` when `None`) are simply absent from
`hook_data` and therefore absent from `t`.

The resulting TOML is:
```toml
[[hook]]
id   = "ruff"
from = "pypi:ruff>=0.4"
run  = "ruff check --fix {files}"
files = "*.py"
```

### `when` inline table

The `when` dict (from `model_dump`) contains only the keys that were present
and non-None/non-default on the `HookWhen` instance. It is converted to a
tomlkit inline table:

```python
def _build_inline_table(when_data: dict[str, object]) -> tomlkit.items.InlineTable:
    wt = tomlkit.inline_table()
    for key, value in when_data.items():
        wt.append(key, value)
    return wt
```

This produces:
```toml
when = { env-not = "SKIP_MYPY" }
```

It MUST NOT be built as a regular table, which would produce `[hook.N.when]`
sub-table syntax and break both AC-5 and the `load_config` round-trip (because
`tomllib` would parse `[hook.N.when]` as a sub-table, not the inline table
`HookWhen` expects).

### `[group.<name>]` — dotted-table headers

Each key in the `group` dict becomes a dotted-table header
(`[group.lint]`, `[group.full]`, etc.). This requires
`tomlkit.table(is_super_table=True)` for the outer `group` key, with one
regular `tomlkit.table()` per group name as a child.

```python
group_super = tomlkit.table(is_super_table=True)
for name, gdef_data in group_dict.items():
    gt = tomlkit.table()
    for key, value in gdef_data.items():
        gt.add(key, value)
    group_super.add(name, gt)
doc.add("group", group_super)
```

This produces:
```toml
[group.lint]
hooks    = ["ruff"]
parallel = true
on-event = "commit"
```

Fields at their defaults (e.g. `parallel = false`, `fail-fast = false`) are
absent because `exclude_defaults=True` already removed them from `gdef_data`.

### File write

```python
path.write_text(tomlkit.dumps(doc), encoding="utf-8")
```

`tomlkit.dumps` converts the document to a string. `write_text` raises
`IsADirectoryError` naturally if `path` is a directory on Linux.

---

## §4 Field-omission rule

```python
config.model_dump(by_alias=True, exclude_none=True, exclude_defaults=True)
```

### Why `exclude_defaults=True` is the correct choice

`dump_config` must produce a minimal, clean config file regardless of how the
`HooksmithConfig` object was constructed. Two construction paths are relevant:

1. **Via `load_config`:** `HooksmithConfig.model_validate(data)` is called by
   `load_config`. Pydantic marks all fields — including those filled in with
   defaults because they were absent from the TOML input — as "set". Therefore
   `exclude_unset=True` on a `model_validate`-constructed object would **not**
   omit default-valued fields, because pydantic treats them as having been set
   by the validation process. `exclude_defaults=True` is required to suppress
   them.

2. **Via direct construction:** `HooksmithConfig()` or
   `HookDef(id="h", **{"from": "pypi:x", "run": "x"})` — fields not supplied
   by the caller take their defaults. `exclude_unset=True` would suppress these
   correctly, but `exclude_defaults=True` also suppresses them (a field at its
   default value is also unset). So `exclude_defaults=True` covers both
   construction paths.

### Combined flags

- `exclude_none=True` — removes fields whose value is `None` (e.g. `files`,
  `when`, `sources`, `env_not`, `on_ci`, `on_event`, `default_registry`).
- `exclude_defaults=True` — removes fields whose value equals the pydantic
  default (e.g. `pass_files=True`, `depends_on=[]`, `parallel=False`,
  `fail_fast=False`).
- `by_alias=True` — emits TOML key names (`from`, `pass-files`, `depends-on`,
  `env-not`, `on-ci`, `fail-fast`, `on-event`, `default-registry`) instead of
  Python attribute names.

Together these three flags produce a dict that needs no further filtering
before being handed to the tomlkit walker.

---

## §5 Public API delta

### `src/hooksmith/config/__init__.py`

Add one import and update `__all__`:

```python
from hooksmith.config.dumper import dump_config
```

`__all__` ordering rule: **alphabetical**, matching the existing convention
established in BUILD-0001-ARCH §2 and BUILD-0002-ARCH §6.

Alphabetical insertion of `"dump_config"` among the existing symbols:

```
ConfigError        → C
dump_config        → d  (lowercase; 'd' sorts after all uppercase in ASCII)
HooksmithConfig    → G
GroupDef           → G
HookDef            → H
SourceSpec         → S
load_config        → l
```

Python's default `sorted()` on strings uses lexicographic byte order, so
uppercase letters sort before lowercase. The correct alphabetical `__all__`
after adding both new symbols is:

```python
__all__ = [
    "ConfigError",
    "HooksmithConfig",
    "GroupDef",
    "HookDef",
    "SourceSpec",
    "dump_config",
    "load_config",
]
```

This places `dump_config` and `load_config` together at the end (both
lowercase-initial), with `dump_config` before `load_config` (`d` < `l`).

---

## §6 File layout

| File | Single responsibility |
|---|---|
| `src/hooksmith/config/dumper.py` | `dump_config` function and private helpers only. No class. |

One new file. No existing files modified beyond `__init__.py` (API delta, §5).

### Internal structure of `dumper.py`

```
dumper.py
├── dump_config(config, path) -> None          # public; exported
├── _build_document(config) -> tomlkit.TOMLDocument  # private helper
├── _build_hook_aot(hook_list) -> tomlkit.AoT  # private helper
├── _build_group_table(group_dict) -> tomlkit.Table  # private helper
└── _build_inline_table(when_data) -> tomlkit.InlineTable  # private helper
```

Private helpers are `_`-prefixed and MUST NOT appear in `__init__.py`'s
`__all__`. They are not part of the public contract.

The helpers are grouped into this single file because they all share the
single concern of TOML serialization. Splitting them into separate files
would violate the one-concern-per-module rule (BUILD-0001 G-4) without adding
any modularity benefit.

### No class needed

There is no mutable state required during serialization. The `config` argument
is immutable in practice (no writes occur during the dump). A flat set of
functions satisfies the SRP without the overhead of a class.

---

## Appendix

- Story: `planning/features/FEAT-0001-config-loader/stories/STY-0003-round-trip-dump.md`
- Build charter: `planning/build-plans/0003-charter.md`
- Predecessor architecture documents:
  - [`0001-architecture-sketch.md`](0001-architecture-sketch.md) — schema and
    `load_config` contract (§3, §4, §7 alias table)
  - [`0002-architecture-decision.md`](0002-architecture-decision.md) — error
    wrapping and `ConfigError` (§2, §3, §6)
- Alias table reference: `0001-architecture-sketch.md` §7
- Sample fixture: `tests/fixtures/check.toml.sample`
- Unit tests (red): `tests/unit/test_config_dumper.py`
- Acceptance tests (red): `tests/integration/test_config_dump_acceptance.py`
