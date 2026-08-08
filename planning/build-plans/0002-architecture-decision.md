---
id: BUILD-0002-ARCH
title: Architecture decision for STY-0002 (error wrapping + position lookup)
parent: BUILD-0002
target_story: STY-0002
status: Locked
date: 2026-05-28
---

# BUILD-0002-ARCH: Error wrapping + position lookup

> **LOCKED CONTRACT.** Lanes B, C, D consume this document. Amends
> [BUILD-0001-ARCH](0001-architecture-sketch.md) §5 only.

---

## 1. Parsing strategy — **Option B (tomllib happy, tomlkit on error)**

Micro-benchmark on `check.toml` (1525 B, 100 iters, `perf_counter_ns`, two runs):

| Strategy | Median | Mean | p95 |
|---|---|---|---|
| A (always tomlkit) | ~10.3–13.3 ms | ~10.7–13.7 ms | ~14.7–19.8 ms |
| B (tomllib only happy) | ~0.41–0.65 ms | ~0.43–0.75 ms | ~0.54–1.9 ms |

**Option B is ~20–25× faster on the happy path** and pays the tomlkit
cost only when `ValidationError` actually fires. `load_config` runs
every invocation, so a sub-ms ceiling matters; the on-error two-parse
penalty is paid only while a user is actively fixing their config,
where the extra ~10 ms is invisible. Bench: `/tmp/bench_strategy.py`.

---

## 2. `ConfigError` shape

```python
# src/hooksmith/config/config_error.py
class ConfigError(ValueError):
    path: Path
    errors: list[tuple[int, int, str]]

    def __init__(self, path: Path, errors: list[tuple[int, int, str]]) -> None: ...
    def __str__(self) -> str: ...  # newline-joined "path:line:col: msg"
```

Contract:

- Subclasses `ValueError` (acceptance #4 — existing `except ValueError:`
  keeps working).
- `__cause__` MUST be set by the caller via
  `raise ConfigError(path, entries) from original_exception`. Tests
  assert `isinstance(exc.__cause__, TOMLDecodeError | ValidationError)`
  per the two-layer test strategy.
- `errors` MUST contain ≥ 1 entry. Constructor raises `ValueError` on
  empty list (defensive; an empty `ConfigError` would have empty
  `__str__`, violating the acceptance #1 regex).
- `__str__` joins entries with `\n` as `f"{self.path}:{line}:{col}: {msg}"`.

---

## 3. Translator function signatures

```python
# src/hooksmith/config/_error_translator.py
def _parse_toml_error(err: tomllib.TOMLDecodeError) -> tuple[int, int, str]: ...

def _locate_validation_errors(
    err: pydantic.ValidationError,
    source: str,
    toml_doc: tomlkit.TOMLDocument,
) -> list[tuple[int, int, str]]: ...
```

Both pure (no I/O, no globals). Private module — never imported from
`__init__.py` (BUILD-0002 §5 enforcement).

`_parse_toml_error`: regex-match `at line (\d+), column (\d+)` against
`str(err)`. Match → `(int(line), int(col), str(err))`. Miss (e.g.
"at end of document") → `(1, 1, str(err))`. Regex is compile-time
constant — no user-controlled input ever reaches `re.compile`.

---

## 4. Position-lookup algorithm

For each `err_dict in err.errors()`:

```
loc = err_dict["loc"]            # ('hook', 0, 'id') or ('group', 'lint', 'parallel')
msg = err_dict["msg"]
formatted = f"{msg} (field: {'.'.join(str(x) for x in loc)})"
try:
    item = walk(toml_doc, loc)        # navigate dict / AoT indices
except (KeyError, IndexError, TypeError):
    item = walk_parent(toml_doc, loc) # typo / extra_forbidden — fall back
(line, col) = locate(item, loc, source)
yield (line, col, formatted)
```

`locate(item, loc, source)`:

1. **Anchor header line** in `source`:
   - AoT (`loc = (..., 'hook', N, ...)`): scan for Nth match of
     `^\s*\[\[hook\]\]\s*$` (multiline).
   - Dotted table (`loc = ('group', 'lint', ...)`): scan for
     `^\s*\[group\.lint\]\s*$`.
   - Top-level scalar (`loc = ('sources',)`): anchor = line 1.

2. **Field line**: terminal `loc` element is the field name. Scan
   forward from anchor for `^\s*<field-name>\s*=`, stopping at next
   `[...]` header. Typo / unknown-key cases (field absent): use anchor
   line, `col = 1`.

3. **`col`** = 1-based column of the field-name's first character.
   Parent-fallback: `col = 1`.

4. Return 1-based `(line, col)`, joined with `msg` from step 0.

**Determinism (H-3).** pydantic v2 returns `err.errors()` in document
order; we emit in that order. Tests pin ordering via field choice.

---

## 5. Loader integration

S3 (size cap) and S4 (regular-file) guards from BUILD-0001-ARCH §5
remain **before** the try block, unchanged:

```python
st = path.stat()
if not stat.S_ISREG(st.st_mode):
    raise OSError(...)               # unchanged
if st.st_size > 1 << 20:
    raise OSError(...)               # unchanged

source = path.read_text(encoding="utf-8")
try:
    data = tomllib.loads(source)     # Option B — stdlib on happy path
except tomllib.TOMLDecodeError as e:
    raise ConfigError(path, [_parse_toml_error(e)]) from e

try:
    return HooksmithConfig.model_validate(data)
except pydantic.ValidationError as e:
    toml_doc = tomlkit.parse(source) # only on error (Option B)
    raise ConfigError(path, _locate_validation_errors(e, source, toml_doc)) from e
```

`FileNotFoundError` / `PermissionError` from `read_text` propagate
unchanged (BUILD-0001-ARCH §5 rows 1 & 2). Only `TOMLDecodeError` and
`ValidationError` are wrapped. Switched from
`tomllib.load(open(path, "rb"))` to `read_text` + `tomllib.loads(source)`
because Option B needs `source` in scope for the translator.

---

## 6. Public API delta

`src/hooksmith/config/__init__.py`:

```python
__all__ = ["ConfigError", "HooksmithConfig", "GroupDef", "HookDef", "SourceSpec", "load_config"]
```

Plus `from hooksmith.config.config_error import ConfigError`.

---

## 7. File layout

| File | Single responsibility |
|---|---|
| `src/hooksmith/config/config_error.py` | `class ConfigError` only. |
| `src/hooksmith/config/_error_translator.py` | `_parse_toml_error` + `_locate_validation_errors` only. Private — never imported from `__init__.py`. |

Both honour python.md one-class-per-file / one-concern-per-module
(BUILD-0001 G-4). Translator has no class — rule satisfied by
aggregation-of-related-helpers.

---

## 8. Error message format

Per pydantic error:

```python
msg = f"{err_dict['msg']} (field: {'.'.join(str(x) for x in err_dict['loc'])})"
```

Full line: `check.toml:5:3: Field required (field: hook.0.id)`. Multi-error
(acceptance #3): one line per error, `\n`-joined, pydantic doc order (§4).

---

## Appendix

- Story: `planning/features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md`
- Build plan: `planning/build-plans/0002-multiagent-build-sty-0002.md`
- Predecessor (amends §5 only): [`0001-architecture-sketch.md`](0001-architecture-sketch.md)
- Bench script: `/tmp/bench_strategy.py`
