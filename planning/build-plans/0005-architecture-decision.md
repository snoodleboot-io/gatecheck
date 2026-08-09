---
id: BUILD-0005-ARCH
title: Architecture decision for STY-0005 (resolve project + system sources)
parent: BUILD-0005
target_story: STY-0005
status: Locked
date: 2026-07-05
---

# BUILD-0005-ARCH: Resolve `project` / `system` sources to concrete executables

> **LOCKED CONTRACT.** The code / test / review lanes consume this document.
> Any change requires re-opening BUILD-0005 §1.

---

## §1 Placement — `hooksmith.sources.resolver` (LOCKED)

### Decision

The resolver lands in the **existing leaf package** `src/hooksmith/sources/`,
alongside `parser.py` — **not** in `hooksmith.env`. `resolve_source` is the
natural second half of the STY-0004 parse→resolve slice: it consumes a
`ParsedSource` (defined here) and produces a single located binary with no
notion of a cached environment.

### Justification

1. **It extends `sources`' own types.** `resolve_source(source: ParsedSource,
   …)` `match`es on the union STY-0004 defined and returns a value object built
   from the same idioms. `parse_source` → `resolve_source` reads as one arc in
   one package.
2. **It stays a pure, dependency-light leaf.** `hooksmith.sources` imports
   nothing from `hooksmith.config` or `hooksmith.env`; keeping the resolver here
   preserves that. It needs only stdlib `os` / `shutil` / `pathlib` / `typing`
   plus the already-present `pydantic`.
3. **`hooksmith.env` is a different abstraction.** `EnvManager.resolve(hook) ->
   ResolvedEnv(bin_dir, cache_key)` is about uv-backed venv creation and caching
   (the Environments feature). STY-0005 produces **no** cache key and creates
   **no** env, so it does not fit that contract. Later, `EnvManager` (or the
   runner) **delegates** the `project` / `system` kinds to `resolve_source` and
   owns only the `pypi:` venv path.
4. **The `env` package is currently uncommitted/gitignored.** Landing the
   resolver there would force this story to un-ignore, commit, and lint-clean
   the whole Environments scaffold — unrelated scope. Placing it in `sources`
   avoids that coupling entirely (see charter § Split-out chore).

---

## §2 Module layout — additions to `src/hooksmith/sources/`

One class / function-group per file (core conventions: filename = snake_case of
the class).

| File | Status | Single responsibility |
|---|---|---|
| `src/hooksmith/sources/resolved_tool.py` | **NEW** | `ResolvedTool` frozen pydantic model. |
| `src/hooksmith/sources/source_resolution_error.py` | **NEW** | `SourceResolutionError(ValueError)`. |
| `src/hooksmith/sources/resolver.py` | **NEW** | `resolve_source(...) -> ResolvedTool` + private helpers. No class. |
| `src/hooksmith/sources/__init__.py` | **EDIT** | Extend imports + `__all__` with the three new symbols. |
| `parsed_source.py`, `pypi_source.py`, `project_source.py`, `system_source.py`, `unsupported_source.py`, `parser.py`, `source_spec_error.py` | UNCHANGED | STY-0004 models / parser — consumed, not modified. |

### `__init__.py` exports / `__all__` (LOCKED)

Alphabetical, uppercase before lowercase (matching STY-0004 §2). The three new
symbols interleave into the existing list:

```python
"""Public facade for hooksmith.sources (BUILD-0004-ARCH §2, BUILD-0005-ARCH §2)."""
from __future__ import annotations

from hooksmith.sources.parsed_source import ParsedSource
from hooksmith.sources.parser import parse_source
from hooksmith.sources.project_source import ProjectSource
from hooksmith.sources.pypi_source import PyPISource
from hooksmith.sources.resolved_tool import ResolvedTool
from hooksmith.sources.resolver import resolve_source
from hooksmith.sources.source_resolution_error import SourceResolutionError
from hooksmith.sources.source_spec_error import SourceSpecError
from hooksmith.sources.system_source import SystemSource
from hooksmith.sources.unsupported_source import UnsupportedSource

__all__ = [
    "ParsedSource",
    "ProjectSource",
    "PyPISource",
    "ResolvedTool",
    "SourceResolutionError",
    "SourceSpecError",
    "SystemSource",
    "UnsupportedSource",
    "parse_source",
    "resolve_source",
]
```

**Net `__all__` additions:** `ResolvedTool`, `SourceResolutionError`,
`resolve_source`. No existing symbol is removed or reordered relative to its
alphabetical slot.

---

## §3 Model spec — `ResolvedTool` (exact types, LOCKED)

Frozen pydantic `BaseModel`, mirroring the STY-0004 source models exactly.

```python
# resolved_tool.py
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResolvedTool(BaseModel):
    """A source kind resolved to a concrete, absolute executable (BUILD-0005-ARCH §3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    executable: Path
    origin: Literal["project", "system"]
```

| Field | Type | Meaning |
|---|---|---|
| `tool` | `str` | The requested command name, echoed back (e.g. `"ruff"`). Bare name, not a path. |
| `executable` | `Path` | The **absolute** path to the resolved executable. Always `Path(...).resolve()`-d by the resolver (AC-11). |
| `origin` | `Literal["project", "system"]` | Which rule produced the result, for runner/cache explainability (PRD-0001 § Goal 5). Only the two resolvable kinds appear; `pypi` / `unsupported` never yield a `ResolvedTool`. |

Notes:
- `ConfigDict(frozen=True, extra="forbid")` → hashable, immutable value object;
  unknown keys rejected. Consistent with `PyPISource` et al.
- pydantic coerces `str` → `Path` for `executable`, but the resolver always
  passes an already-resolved `Path`, so no relative path can enter (AC-11). The
  model does **not** re-validate absoluteness (validation lives in the resolver
  so the not-found message is authoritative); the resolver is the single
  producer.
- No `kind` field — `ResolvedTool` is an output value, not a member of the
  `ParsedSource` discriminated union.

---

## §4 `resolve_source` — signature, algorithm & error table (LOCKED)

### Signature

```python
# resolver.py
from collections.abc import Mapping
from pathlib import Path

from hooksmith.sources.parsed_source import ParsedSource
from hooksmith.sources.resolved_tool import ResolvedTool


def resolve_source(
    source: ParsedSource,
    tool: str,
    *,
    workspace_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedTool: ...
```

- **`source`** — the classified `ParsedSource` from `parse_source(hook.from_)`.
  Only `SystemSource` / `ProjectSource` resolve.
- **`tool`** — the executable/command name to locate (bare name, not a path);
  the first shell token of `HookDef.run`. The resolver does **not** tokenize
  `run` (runner's concern).
- **`workspace_root`** — project root under which `.venv` is discovered for
  `ProjectSource`. `None` → `Path.cwd()` (resolved at call time, inside the
  function).
- **`environ`** — env mapping read for `PATH` (system) and `VIRTUAL_ENV`
  (project). `None` → `os.environ`. Injectable so tests are hermetic and the
  function is a pure function of its inputs + filesystem state.

Both defaults are resolved **inside** the function body (`environ = os.environ
if environ is None else environ`; `root = Path.cwd() if workspace_root is None
else workspace_root`) — never as mutable default arguments.

### Control flow — `match` over the source kind

```python
match source:
    case SystemSource():
        return _resolve_system(tool, environ)
    case ProjectSource():
        return _resolve_project(tool, root, environ)
    case PyPISource():
        raise SourceResolutionError(tool, "pypi", <pypi reason>)
    case UnsupportedSource(scheme=scheme):
        raise SourceResolutionError(tool, "unsupported", <unsupported reason>)
```

The union is plain (STY-0004 §1), so each `case` narrows cleanly under
`mypy --strict` (AC-15). No `case _:` fallthrough is needed — the four cases are
exhaustive over `ParsedSource` — but a defensive final
`case _:  # pragma: no cover` may be added only if `mypy` requires exhaustiveness
proof; it must not swallow a real kind.

#### `SystemSource` branch — `_resolve_system(tool, environ)`

1. `path_value = environ.get("PATH")` (may be `None`; `shutil.which` then falls
   back to `os.defaultpath`, which is acceptable — the caller injects `PATH` for
   hermetic tests).
2. `located = shutil.which(tool, path=path_value)` — standard `which` semantics:
   first directory in `PATH` order with an executable match wins.
3. If `located is None` → raise `SourceResolutionError(tool, "system", "not
   found on PATH")`.
4. Else → `ResolvedTool(tool=tool, executable=Path(located).resolve(),
   origin="system")`.

#### `ProjectSource` branch — `_resolve_project(tool, root, environ)`

Locate `tool` in the project's own **already-existing** environment, in this
**precedence order** (first qualifying candidate wins):

1. **Active venv:** if `environ.get("VIRTUAL_ENV")` is set **and non-empty** →
   candidate `Path(VIRTUAL_ENV) / "bin" / tool`.
2. **Discovered project venv:** candidate `root / ".venv" / "bin" / tool`
   (`root = workspace_root or Path.cwd()`).

A candidate **qualifies** only if all hold:
- it **exists** and is a **regular file following symlinks** — `candidate.is_file()`
  (pathlib `is_file()` follows symlinks and returns `False` for a missing or
  broken-symlink path), and
- it is **executable** — `os.access(candidate, os.X_OK)`.

The first qualifying candidate → `ResolvedTool(tool=tool,
executable=candidate.resolve(), origin="project")`. If **neither** qualifies →
raise `SourceResolutionError(tool, "project", "not found in project environment
(checked $VIRTUAL_ENV/bin and <workspace_root>/.venv/bin)")`. A missing `.venv`
is a not-found error — **never** a trigger to create one (AC-9).

> Candidate list construction: build the ordered candidate list first (0, 1, or
> 2 entries depending on whether `VIRTUAL_ENV` is set+non-empty), then return the
> first that qualifies. This keeps precedence explicit and the loop trivially
> testable.

#### `PyPISource` / `UnsupportedSource` branches

Raise `SourceResolutionError` immediately — no network, no crash (AC-8). Single
error type; the caller branches on `.kind`.

### Error message table (exact `reason` strings — LOCKED)

| Branch | `kind` | `reason` | Full message |
|---|---|---|---|
| system, tool absent | `system` | `not found on PATH` | `cannot resolve 'ruff' from system source: not found on PATH` |
| project, tool absent | `project` | `not found in project environment (checked $VIRTUAL_ENV/bin and <workspace_root>/.venv/bin)` | `cannot resolve 'ruff' from project source: not found in project environment (checked $VIRTUAL_ENV/bin and <workspace_root>/.venv/bin)` |
| pypi (out of scope) | `pypi` | `pypi source resolution is delegated to Environments (STY-0006), not handled here` | `cannot resolve 'ruff' from pypi source: pypi source resolution is delegated to Environments (STY-0006), not handled here` |
| unsupported scheme | `unsupported` | `'<scheme>' sources are not supported` | `cannot resolve 'x' from unsupported source: 'git' sources are not supported` |

- The **project** `reason` uses the literal text `$VIRTUAL_ENV/bin` and
  `<workspace_root>/.venv/bin` (not the interpolated paths) — it names the
  *locations probed*, matching AC-6 and staying location-agnostic in the string.
- The **unsupported** `reason` interpolates the concrete `scheme`
  (`local` / `git` / `docker`) captured from `UnsupportedSource(scheme=...)`.
- `kind` on the error equals the source's own `.kind` value in every branch.

### Determinism / purity (AC-9, AC-10)

Given the same `(source, tool, PATH, VIRTUAL_ENV, workspace_root, filesystem
state)`, `resolve_source` returns an equal `ResolvedTool` (or raises the same
error) on every call. It performs **no network, no subprocess, no writes** —
only `PATH`/dir reads (`shutil.which`), `is_file()`, and `os.access` checks.
Repeated calls mutate nothing. Verifiable by inspection; hermetic `tmp_path` +
monkeypatched `environ` tests need no mocks of the filesystem.

---

## §5 Why `SourceResolutionError` does NOT map to `ConfigError` (LOCKED)

`SourceResolutionError(ValueError)` in `source_resolution_error.py` mirrors
`SourceSpecError`'s shape — subclasses `ValueError`, carries structured fields,
is location-free:

```python
# source_resolution_error.py
from __future__ import annotations


class SourceResolutionError(ValueError):
    """Raised by resolve_source when a source cannot be located (BUILD-0005-ARCH §5)."""

    tool: str
    kind: str        # the source's `.kind` — "system" | "project" | "pypi" | "unsupported"
    reason: str

    def __init__(self, tool: str, kind: str, reason: str) -> None:
        self.tool = tool
        self.kind = kind
        self.reason = reason
        super().__init__(f"cannot resolve '{tool}' from {kind} source: {reason}")
```

**It does not map to `ConfigError`.** Unlike `SourceSpecError` — a *syntax*
error in `check.toml`, knowable at **load time** and wrapped by the config layer
with `path:line:col` (STY-0004 §6) — a resolution failure is a
**runtime/environment** condition: the `from` and `run` are syntactically valid,
but the tool is absent *on this machine right now*. It has no
`check.toml:line:col` meaning.

Therefore:
- `SourceResolutionError` is **not** raised from `load_config` and is **not**
  wrapped as `ConfigError`. Loading a config whose tool happens to be absent
  still **succeeds** (AC-13). `load_config` is unchanged by this build.
- It surfaces at **resolve/run time** — the runner calls `resolve_source` and
  catches it, reporting the hook that failed to resolve. The runner **may**
  attach the offending hook id for context (analogous to STY-0004's `(hook: …)`
  suffix), but STY-0005's resolver itself stays **hook-unaware and
  location-free** — it knows only `tool` / `kind` / `reason`.

Contrast table:

| | `SourceSpecError` (STY-0004) | `SourceResolutionError` (STY-0005) |
|---|---|---|
| Nature | Syntax error in the `from` string | Environment/runtime condition |
| Knowable at | Config load time | Resolve/run time |
| Has `check.toml:line:col`? | Yes (config layer recovers it) | No |
| Wrapped as `ConfigError`? | **Yes**, eagerly in `load_config` | **No** |
| Surfaces from | `load_config` | `resolve_source` (runner catches) |

---

## §6 Cross-platform — POSIX `bin/` only in v1 (LOCKED, Windows deferred)

- v1 probes **POSIX `bin/`** only for `ProjectSource` (`<VIRTUAL_ENV>/bin/<tool>`,
  `<root>/.venv/bin/<tool>`). This matches PRD-0001 § Open questions (Windows is
  a fast-follower).
- The Windows `Scripts\` layout and `.exe` / `PATHEXT` handling are **explicitly
  deferred** — not built here. `shutil.which` on the `system` branch already
  honours `PATHEXT` on Windows, but the `project` branch's hard-coded `bin`
  segment and lack of `.exe` probing mean project resolution is POSIX-only in
  v1.
- **Locked later decision:** whether `ResolvedTool.origin` or the candidate list
  gains a Windows branch is deferred to the fast-follower. `ResolvedTool`'s shape
  (`tool` / `executable` / `origin`) is forward-compatible: a Windows branch adds
  candidate paths, not fields.

---

## §7 Import direction / no cycle (LOCKED)

- `hooksmith.sources` (including the three new modules) imports **only** stdlib
  (`os`, `shutil`, `pathlib`, `collections.abc`, `typing`), `pydantic`, and its
  **own** sibling modules (`parsed_source`, the four kind-models, `resolved_tool`).
- It imports **nothing** from `hooksmith.config` or `hooksmith.env` at runtime.
  `resolve_source` receives `tool` as an explicit string rather than a `HookDef`,
  precisely so `sources` need not import `config`.
- **No dependency on `hooksmith.env`.** The resolver does not touch the env
  package; the `.gitignore` un-ignore is a separate chore (charter § Split-out).
- **Import direction:** `config` → `sources` (one-directional; STY-0004 §6
  wired `config/_error_translator.py` + `config/loader.py` to import
  `parse_source` / `SourceSpecError`). `sources` → nothing internal but its own
  package. `env` → `config` (+ will later → `sources` via delegation). **No
  cycle:** `sources` remains a leaf.

---

## §8 mypy --strict cleanliness (LOCKED)

- `from __future__ import annotations` in every new module.
- Every function fully annotated; `resolve_source(source: ParsedSource, tool:
  str, *, workspace_root: Path | None = None, environ: Mapping[str, str] | None
  = None) -> ResolvedTool`; private helpers `_resolve_system(tool: str, environ:
  Mapping[str, str]) -> ResolvedTool` and `_resolve_project(tool: str, root:
  Path, environ: Mapping[str, str]) -> ResolvedTool`.
- The `match source:` narrows `SystemSource` / `ProjectSource` /
  `PyPISource` / `UnsupportedSource` cleanly because `ParsedSource` is a plain
  union (AC-15).
- `environ: Mapping[str, str]` (read-only `collections.abc.Mapping`, not
  `dict`) — accepts `os.environ` and test dicts without variance issues.
- `shutil.which` returns `str | None`; the `None` branch raises, so no
  `Optional` leaks into `Path(...)`.
- **No `# type: ignore`** introduced anywhere in the new code.
- `origin` / `kind` string literals are typed by the `Literal` on `ResolvedTool`;
  no `Any` leaks.

## §9 pydantic knobs (LOCKED)

- `ConfigDict(frozen=True, extra="forbid")` on `ResolvedTool` (identical idiom
  to the STY-0004 source models).
- `executable: Path` — pydantic accepts a `Path`; the resolver passes an
  already-`resolve()`-d absolute `Path`.
- `origin: Literal["project", "system"]` — statically typed discriminant of
  which rule fired; no default (always supplied by the resolver).
- No validators — absoluteness/existence validation lives authoritatively in
  `resolve_source` so the not-found message is the spec'd one; the model is a
  value carrier.
- `SourceResolutionError` is a **plain `ValueError` subclass**, not a pydantic
  model (mirrors `SourceSpecError`).

---

## §10 Explicitly OUT of scope (re-stated)

- `PyPISource` network/registry resolution + venv creation (STY-0006 /
  Environments) — rejected with a typed error.
- `UnsupportedSource` (`local:` / `git:` / `docker:`) beyond a typed rejection.
- Tokenizing `HookDef.run` into command + args; running the executable
  (Runner). `tool` is an explicit input.
- Workspace discovery (walking up for `check.toml` / `pyproject.toml`) —
  `workspace_root` is an input (default `Path.cwd()`).
- Windows `Scripts\` / `.exe` / `PATHEXT` project-branch handling (§6).
- Cache key / hit-miss explainability (Cache feature) — `origin` is carried, no
  cache key produced.
- The `.gitignore` `env/` un-ignore + committing `src/hooksmith/env/` — separate
  chore (charter § Split-out; STY-0005 TSK-008).
- Any new public symbol on `hooksmith.config`; any new runtime dependency.

---

## Appendix

- Story:
  `planning/features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md`
- Feature: `planning/features/FEAT-0002-source-resolution/feature.md`
- Build charter: `planning/build-plans/0005-charter.md`
- Predecessor architecture documents:
  - `0004-architecture-decision.md` — `hooksmith.sources` package, frozen-model
    idiom, `ParsedSource` plain-union, `__all__` ordering, `SourceSpecError`,
    import direction (`config` → `sources`).
- Consumed (unchanged) STY-0004 code:
  - `src/hooksmith/sources/parsed_source.py` — `ParsedSource` union (the `match`
    surface).
  - `src/hooksmith/sources/{system,project,pypi,unsupported}_source.py` — the
    four `kind`-models.
- Config references (read for §5 justification, not modified):
  - `src/hooksmith/config/config_error.py` — `ConfigError(path, [(line, col,
    msg)])` (why resolution errors do NOT map here).
  - `src/hooksmith/config/hook_def.py` — `HookDef.run` / `from_` (where the
    runner derives `tool`; resolver takes `tool` explicitly).
- New unit tests (red): `tests/unit/test_source_resolve.py`.
- New acceptance tests (red):
  `tests/integration/test_source_resolution_acceptance.py`.
