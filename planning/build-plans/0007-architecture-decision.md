---
id: BUILD-0007-ARCH
title: Architecture decision for STY-0007 (EnvManager skeleton + non-venv path; pypi deferred)
parent: BUILD-0007
target_story: STY-0007
status: Locked
date: 2026-07-05
---

# BUILD-0007-ARCH: `EnvManager` skeleton + the non-venv path (`project` / `system` → `ResolvedEnv`); `pypi` deferred

> **LOCKED CONTRACT.** The code / test / review lanes consume this document.
> Any change requires re-opening BUILD-0007 §1.

> **Design gate (APPROVED, build to these):**
> 1. Tool name is derived as **`shlex.split(hook.run)[0]`** — NO `HookDef.tool`
>    schema change, no new config field.
> 2. STY-0007 is the **non-venv path only**: `project` / `system` → `ResolvedEnv`;
>    `pypi` / `pypi+alias:` / unsupported → `EnvError`. **NO subprocess, NO network,
>    NO venv creation, NO filesystem writes** (that is STY-0008). Pure / hermetic.
> 3. **No new runtime dependency** — stdlib only (`shlex`, `hashlib`, `pathlib`,
>    `collections.abc`).

---

## §1 Placement — build out the existing `gatecheck.env` leaf (LOCKED)

### Decision

The work lands entirely inside the **existing** leaf package
`src/gatecheck/env/`. `EnvManager` and `ResolvedEnv` already live in
`manager.py` (scaffolding); this story builds them out and adds one new sibling
(`env_error.py`). No new package, no code outside `src/gatecheck/env/`.

This completes a clean, acyclic three-way split of source handling +
environments:

- **`gatecheck.sources`** — classify a `from` spec (`parse_source`) and locate the
  local kinds (`resolve_source`). Pure, no I/O. **Unchanged by this story.**
- **`gatecheck.registry`** — pin a `pypi:` requirement to a concrete distribution
  (network + `packaging`). **Not consumed here** (STY-0008 consumes it).
- **`gatecheck.env`** — turn a `HookDef` into an executable environment
  (`EnvManager.resolve`). **This story** — the non-venv path only.

### Justification

1. **Character preservation.** `env` is the environment-management leaf; keeping
   the dispatch + `cache_key` derivation here (rather than in `sources`) mirrors the
   STY-0006 decision that kept the network resolver out of the pure `sources`
   leaf. `EnvManager` orchestrates the two existing leaves; it does not reshape
   them.
2. **`resolve_source` contract stays verbatim.** `EnvManager` calls
   `resolve_source(source, tool, workspace_root=…, environ=…)` for
   `SystemSource` / `ProjectSource` and forwards the injected seams. `resolve_source`
   is **not touched**.
3. **Different failure domain.** Env-management failures (unresolvable tool name,
   deferred `pypi`, unsupported kind) carry `hook_id` / `reason`, not `tool` /
   `kind` (that is `SourceResolutionError`) nor `requirement` / `index_url` (that is
   `RegistryError`). A dedicated `EnvError` (SRP) keeps the domains apart.
4. **Import direction stays acyclic.** `gatecheck.env` imports `gatecheck.sources`
   (`parse_source`, `resolve_source`, the `ParsedSource` members, the two source
   errors) and `gatecheck.config` (`HookDef`) — both leaves. Nothing imports
   `gatecheck.env` back in this slice. See §9.

---

## §2 Module layout — `src/gatecheck/env/` (LOCKED)

One class / function-group per file (core conventions: filename = snake_case of
the class). Names follow the story's file table verbatim.

| File | Status | Single responsibility |
|---|---|---|
| `src/gatecheck/env/env_error.py` | **NEW** | `EnvError(ValueError)` with structured `hook_id` / `reason` and the `cannot resolve environment for hook '<id>': <reason>` message. |
| `src/gatecheck/env/manager.py` | **EDIT (build out)** | `EnvManager` (constructor state + `resolve` dispatch + private `_derive_tool` / `_cache_key`) **and** the `ResolvedEnv` frozen dataclass, which stays here (see §3 / §5). |
| `src/gatecheck/env/__init__.py` | **EDIT** | Facade — export `EnvError`, `EnvManager`, `ResolvedEnv`; set `__all__` (alphabetical, uppercase-first). |

### `__init__.py` exports / `__all__` (LOCKED)

Alphabetical, uppercase before lowercase (matching `gatecheck.sources` §2 /
`gatecheck.registry` §2 style). All three symbols are classes, so all uppercase.

```python
"""Public facade for gatecheck.env (BUILD-0007-ARCH §2)."""

from __future__ import annotations

from gatecheck.env.env_error import EnvError
from gatecheck.env.manager import EnvManager, ResolvedEnv

__all__ = [
    "EnvError",
    "EnvManager",
    "ResolvedEnv",
]
```

AC-14 requires `from gatecheck.env import EnvManager, ResolvedEnv, EnvError` to
work — satisfied above. (The current stub's module docstring
`"""Per-hook environment management (uv-backed venvs)."""` may stay or be kept;
no behavioural meaning.)

### Why `env_error.py` is a separate module and `ResolvedEnv` is **not**

- **`env_error.py` is split out** per the one-class-per-file rule and to mirror the
  established `source_resolution_error.py` / `source_spec_error.py` /
  `registry_error.py` pattern (each typed error in its own file). This keeps the
  error importable independently and localizes the message format.
- **`ResolvedEnv` stays in `manager.py`** — a deliberate, story-sanctioned
  exception to strict one-class-per-file (the story's file table says *"`ResolvedEnv`
  stays here"*). Rationale: it is the small output value object of `EnvManager`, the
  existing stub already colocates them, and STY-0008 / STY-0009 / the runner import
  it as `gatecheck.env.ResolvedEnv` via the facade regardless of file. Splitting it
  into `resolved_env.py` now would be a gratuitous move of a tracked interface with
  no import-site benefit (the facade re-exports it either way). **Locked: keep it in
  `manager.py`.**

---

## §3 `ResolvedEnv` — final shape (LOCKED: frozen dataclass, unchanged)

**Decision: `ResolvedEnv` stays a `@dataclass(frozen=True)` exactly as the existing
stub defines it — it is NOT migrated to the frozen-pydantic idiom used by
`ResolvedTool` / `ResolvedPyPISource`.**

```python
# manager.py (unchanged from the stub)
@dataclass(frozen=True)
class ResolvedEnv:
    """An environment ready to execute a hook's command."""

    bin_dir: Path
    cache_key: str
```

| Field | Type | Meaning |
|---|---|---|
| `bin_dir` | `Path` | The directory containing the hook's executable — the parent of the resolved executable (`ResolvedTool.executable.parent`). The dir the runner adds to `PATH` / runs the command from. Always an already-existing directory for `project` / `system`; **never created** (AC-16). |
| `cache_key` | `str` | 64-char lowercase SHA-256 hex digest deterministically identifying this environment (§6). |

### Justification (dataclass vs frozen pydantic)

`ResolvedTool` and `ResolvedPyPISource` are frozen **pydantic** models. `ResolvedEnv`
deviates from that idiom **deliberately**, and the deviation is locked:

1. **Tracked, contract-stable interface.** The story locks *"`ResolvedEnv(bin_dir,
   cache_key)` is kept exactly as the existing stub defines it so STY-0008/STY-0009
   and the runner build on an unchanged shape"* and AC-5 reasons about equality
   *"since `ResolvedEnv` is a frozen dataclass"*. Changing the base class is a
   silent contract change to a shape three downstream stories consume.
2. **No validation / serialization need.** `ResolvedEnv` is an internal *output*
   value object built solely by `EnvManager` from already-validated, already-typed
   inputs (`Path`, `str`). Unlike `ResolvedTool` / `ResolvedPyPISource` (which are
   constructed from parsed external data), it never validates untrusted input and is
   never (de)serialized from TOML/JSON. Pydantic's validation / `model_config` buys
   nothing here.
3. **Equality + immutability for free, zero deps.** `@dataclass(frozen=True)` gives
   structural `__eq__` and `__hash__` and immutability — exactly what AC-5
   (`ResolvedEnv` equality across two calls) needs — with no dependency and no
   coercion surprises (e.g. pydantic `Path` normalization).

**Flag (tracked interface):** this is the one shape in the source/env stack that is
a stdlib dataclass rather than a pydantic model. It is intentional and locked; a
future migration must treat it as a breaking contract change across STY-0008 /
STY-0009 / the runner.

---

## §4 `EnvError(ValueError)` — spec (LOCKED)

```python
# env_error.py
from __future__ import annotations


class EnvError(ValueError):
    """Raised by EnvManager.resolve when a hook cannot be resolved to an environment (BUILD-0007-ARCH §4).

    Mirrors SourceResolutionError / RegistryError — subclasses ValueError, carries
    structured fields, is location-free. An env-resolution failure is a
    runtime/environment-domain condition (unresolvable tool name, a source kind not
    handled in this slice), NOT a check.toml syntax error, so it does NOT map to
    ConfigError and carries no line:col.
    """

    hook_id: str
    reason: str

    def __init__(self, hook_id: str, reason: str) -> None:
        self.hook_id = hook_id
        self.reason = reason
        super().__init__(f"cannot resolve environment for hook '{hook_id}': {reason}")
```

- **Subclasses `ValueError`** — consistent with `SourceSpecError` /
  `SourceResolutionError` / `RegistryError` / `ConfigError`. (AC-12)
- **Structured fields** `hook_id` / `reason` (declared at class level like
  `SourceResolutionError`'s `tool` / `kind` / `reason`), so callers can branch on
  them without string parsing.
- **Message form:** `cannot resolve environment for hook '<id>': <reason>`
  (AC-12).
- **Location-free / runtime.** Does **not** map to `ConfigError`, carries no
  `line:col` — the mistake is not a config-syntax error (mirrors
  `SourceResolutionError` §5 / `RegistryError` §6 reasoning).

### Cases `EnvError` OWNS (raised by `EnvManager` itself)

| Case | `reason` (LOCKED text) |
|---|---|
| `run` yields no tool name (empty `shlex.split`, e.g. whitespace-only) | `cannot derive a tool name from run = '<run>'` |
| `run` has unbalanced quotes (`shlex.split` raises `ValueError`) | `cannot derive a tool name from run = '<run>'` |
| `pypi:` / `pypi+alias:` (`PyPISource`) | `environment creation for pypi sources is deferred to STY-0008` |
| `local:` / `git:` / `docker:` (`UnsupportedSource(scheme=…)`) | `'<scheme>' sources are not supported` |

- The two tool-name cases share one `reason` (both are "cannot derive a tool
  name"); the offending `run` string is embedded so the message is actionable
  (AC-9). Implementation raises the same `EnvError` from the empty-list branch and
  the `except ValueError` branch.
- The `pypi` reason names STY-0008 explicitly (AC-7); this is the exact branch
  STY-0008 replaces with resolve-and-build logic.
- The unsupported reason echoes the recognized `scheme` from
  `UnsupportedSource.scheme` (`"local"` / `"git"` / `"docker"`) (AC-8), matching the
  wording `resolve_source` uses for the same kinds (`'<scheme>' sources are not
  supported`).

### Errors `EnvManager` does NOT own (propagate UNCHANGED)

| Condition | Error | Wrapped? |
|---|---|---|
| Malformed `from` spec | `SourceSpecError` (from `parse_source`) | **No** — propagates unchanged (config-syntax error, already typed). (AC-11) |
| `project` / `system` tool not found | `SourceResolutionError` (from `resolve_source`, carrying `tool` / `kind` / `reason`) | **No** — propagates unchanged. (AC-10) |

**Decision — `EnvManager` does not re-wrap the FEAT-0002 errors.** They are already
typed `ValueError` subclasses with structured fields and good messages; wrapping
them in `EnvError` would hide `tool` / `kind` / `reason` / the `line:col` a
`SourceSpecError` may carry. `EnvError` is introduced *only* for the four
env-domain cases above. (This resolves the story's open "wrap vs propagate"
question in favour of propagate — the story's recommendation.)

---

## §5 `EnvManager` — constructor + `resolve` algorithm (LOCKED)

### Constructor

```python
# manager.py
class EnvManager:
    def __init__(
        self,
        workspace_root: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._environ = environ
```

- `workspace_root` / `environ` are **stored as-is** (including `None`) and passed
  **straight through** to `resolve_source`, which resolves the defaults lazily
  (`None` → `Path.cwd()` / `os.environ`) inside its own body. `EnvManager` therefore
  holds `None` and forwards it — it does **not** eagerly bind `Path.cwd()` /
  `os.environ` at construction, keeping the class a pure, deterministic function of
  its injected inputs for hermetic tests.
- **No `cache_root` / uv-path / client parameters** are added now (STY-0008 /
  STY-0009 own those). Minimal surface, open for extension; the runner constructs
  `EnvManager` once and reuses it.

### `resolve(hook: HookDef) -> ResolvedEnv` — algorithm

`resolve` is a pure function of `(hook, self._workspace_root, self._environ,
filesystem state)`. Steps:

1. **Classify the source.** `source = parse_source(hook.from_)` → `ParsedSource`.
   `parse_source` may raise `SourceSpecError` for a malformed spec — it
   **propagates unchanged** (§4, AC-11). *(`hook.from_` is loader-validated
   non-empty, but a malformed non-empty spec can still raise here.)*
2. **Derive the tool name** via the private helper `_derive_tool(hook)` (see
   below) → `tool: str`. This may raise `EnvError` (AC-9). Ordering note: source
   classification (step 1) runs before tool derivation, so a malformed `from`
   surfaces its `SourceSpecError` first; both are deterministic.
3. **Dispatch on the `ParsedSource` kind** with `match` (mirroring
   `resolve_source`):

```python
match source:
    case SystemSource() | ProjectSource():
        resolved = resolve_source(
            source,
            tool,
            workspace_root=self._workspace_root,
            environ=self._environ,
        )
        return ResolvedEnv(
            bin_dir=resolved.executable.parent,
            cache_key=self._cache_key(resolved),
        )
    case PyPISource():
        raise EnvError(
            hook.id,
            "environment creation for pypi sources is deferred to STY-0008",
        )
    case UnsupportedSource(scheme=scheme):
        raise EnvError(hook.id, f"'{scheme}' sources are not supported")
```

- **`SystemSource` / `ProjectSource`** → call `resolve_source` (forwarding the
  stored seams) → `ResolvedTool`. Build `ResolvedEnv(bin_dir=resolved.executable
  .parent, cache_key=_cache_key(resolved))`. `resolve_source` may raise
  `SourceResolutionError` (tool absent) — **propagates unchanged** (§4, AC-10).
  `resolved.executable` is already an absolute `.resolve()`-d path, so
  `.parent` is an existing absolute directory; **no directory is created** (AC-16).
- **`PyPISource`** → raise the deferred `EnvError` **before** any `resolve_source`
  call (AC-7). This is the single seam STY-0008 replaces (with
  `registry.resolve_pypi_source` + `uv`).
- **`UnsupportedSource(scheme=…)`** → raise the unsupported `EnvError`,
  echoing the recognized scheme (AC-8).

> **Combined `case SystemSource() | ProjectSource():`** — both take the identical
> `resolve_source` path; the `origin` distinction (`"project"` vs `"system"`) is
> carried by `ResolvedTool.origin`, which `resolve_source` sets, and flows into
> `cache_key` (§6) — so the same executable reached two ways still keys distinctly
> (AC-6) without needing two separate `match` arms.

### `_derive_tool(hook: HookDef) -> str` (the tool-name rule, LOCKED)

```python
import shlex

def _derive_tool(hook: HookDef) -> str:
    try:
        tokens = shlex.split(hook.run)
    except ValueError:  # unbalanced quotes, etc.
        raise EnvError(hook.id, f"cannot derive a tool name from run = '{hook.run}'") from None
    if not tokens:
        raise EnvError(hook.id, f"cannot derive a tool name from run = '{hook.run}'")
    return tokens[0]
```

- **`shlex.split(hook.run)[0]`** (POSIX mode) — a quoted / escaped program name is
  tokenized the way the runner will eventually tokenize the command; `str.split()`
  is **not** used (it would mishandle quotes) and no `HookDef.tool` field is added
  (design gate). (AC-3)
- **Empty result** (`run` is whitespace-only — passes `min_length=1` but yields no
  tokens) → `EnvError`. (AC-9)
- **`ValueError` from `shlex`** (unbalanced quotes) → `EnvError` (chained with
  `from None` to keep the message clean; the offending `run` is already in the
  reason). (AC-9)
- Only the **first token** is used; remaining argv tokens are the runner's concern.

### `mypy --strict` exhaustiveness (AC-15)

`ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource`
(four members). The `match` has arms for all four (`SystemSource() |
ProjectSource()`, `PyPISource()`, `UnsupportedSource(scheme=…)`), and **every arm
either `return`s or `raise`s**, so:

- there is no implicit fall-through and no "missing return" for the `-> ResolvedEnv`
  signature, and
- the `match` is exhaustive over the union — `mypy --strict` is satisfied **without**
  a `case _:` catch-all.

**No catch-all is added** (mirroring `resolve_source`, which passes `--strict` the
same way). Adding `case _: assert_never(...)` would be dead code today and would
*mask* a future 5th `ParsedSource` kind at type-check time — omitting it means a new
kind fails `mypy` exhaustiveness loudly, which is the desired behaviour.

---

## §6 `_cache_key` — exact derivation (LOCKED)

```python
import hashlib

_CACHE_KEY_SCHEME = "env-v1"

def _cache_key(self, resolved: ResolvedTool) -> str:
    material = "\n".join(
        [_CACHE_KEY_SCHEME, resolved.origin, str(resolved.executable)]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()  # 64-char lowercase hex
```

Equivalent byte string: `b"env-v1\n" + origin.encode() + b"\n" +
str(executable).encode()` — i.e. `"env-v1\n<origin>\n<absolute executable path>"`,
UTF-8, SHA-256, full 64-char lowercase hex digest. (AC-4)

- **Inputs (LOCKED):**
  1. the **scheme tag** `_CACHE_KEY_SCHEME = "env-v1"` — namespaces the derivation
     so the format can evolve;
  2. `ResolvedTool.origin` — `"project"` or `"system"`, so the **same binary
     reached two ways keys distinctly** (AC-6);
  3. `str(ResolvedTool.executable)` — the **absolute, `.resolve()`-d executable
     path** `resolve_source` returns.
- **Determinism (AC-5).** `resolve_source` returns a `Path(...).resolve()`-d
  absolute path that is a deterministic function of `(source, tool, PATH /
  VIRTUAL_ENV, workspace_root, filesystem state)`; hashing the same `(scheme,
  origin, path)` therefore yields an identical `cache_key` across calls / processes.
  Combined with the frozen `ResolvedEnv`, two `resolve` calls with the same inputs
  and filesystem state produce an **equal `ResolvedEnv`**.
- **Full digest, no truncation.** The full 64-char hex is used (AC-4 pins 64
  chars); no prefix truncation — collision headroom is effectively unbounded for
  this key space, and STY-0009 explainability displays / compares the full key.
- **Forward-compatibility (why the `env-vN` tag).** STY-0008's uv-backed venvs will
  derive their key from the **same scheme tag** but over the pinned
  `name`+`version`+`index_url` (content-addressing the venv). The `env-vN` prefix
  keeps both derivations in **one namespace** and lets STY-0009 explain either.
  Should the material ever change, the tag bumps to `env-v2` so old and new keys
  never collide silently. Localizing the exact material in one private
  `_cache_key(...)` helper keeps the decision in a single place.
- **Collision / uniqueness.** SHA-256 over `(scheme, origin, absolute path)` makes
  collisions cryptographically negligible; distinctness is guaranteed for distinct
  `(origin, path)` pairs (the load-bearing identity of a non-venv environment).

---

## §7 Typing / dependency strategy (LOCKED)

- **No new runtime dependency.** `shlex`, `hashlib`, `pathlib.Path`,
  `collections.abc.Mapping`, `dataclasses.dataclass` are all stdlib. `uv` and
  `packaging` are **not** involved in this slice (AC-13, story Notes).
- **`from __future__ import annotations`** at the top of every touched/new module;
  every function, method, and `EnvError.__init__` fully annotated.
- **`mypy --strict src/gatecheck/env/`** passes with **no new errors and no
  `# type: ignore`** (AC-15). The `match` over `ParsedSource` is exhaustive (§5);
  `resolved.executable.parent` is `Path`; `hashlib.sha256(...).hexdigest()` is
  `str`; `_derive_tool` returns `str`. No `Any` leaks.
- Import set for `manager.py`: stdlib (`__future__`, `dataclasses`, `hashlib`,
  `shlex`, `collections.abc.Mapping`, `pathlib.Path`); `gatecheck.config.hook_def
  .HookDef`; from `gatecheck.sources` — `parse_source`, `resolve_source`,
  `ProjectSource`, `PyPISource`, `SystemSource`, `UnsupportedSource` (and, if a
  local annotation is used, `ResolvedTool`); `gatecheck.env.env_error.EnvError`.
  Grouped stdlib → internal per core conventions.

---

## §8 Hermetic testing seam (LOCKED)

- **No network, no subprocess, no venv creation, no filesystem writes** anywhere in
  `resolve` (AC-13, AC-16). The only I/O is the **read-only filesystem lookup**
  `resolve_source` already performs (`shutil.which` on an injected `PATH`;
  `Path.is_file()` / `os.access` on `$VIRTUAL_ENV/bin` and `<root>/.venv/bin`).
- **The whole seam is the injected `workspace_root` + `environ`** (forwarded to
  `resolve_source`) — exactly `resolve_source`'s own hermetic seam. Tests build a
  `tmp_path` fake `.venv/bin/<tool>` (executable) and/or a fake `PATH` dir and pass
  `environ={"PATH": …}` / `environ={"VIRTUAL_ENV": …}`; no monkeypatching of
  `os.environ` is required.
- **Determinism** (AC-5) follows from `resolve` being a pure function of its
  injected inputs + filesystem state.
- Test files (per story): `tests/unit/test_env_manager.py` (hermetic unit coverage
  of every branch — system/project resolve, `cache_key` shape / determinism /
  `project`≠`system`, `pypi`/`pypi+alias:` → `EnvError`, unsupported → `EnvError`,
  whitespace/unbalanced `run` → `EnvError`, tool-not-found → `SourceResolutionError`
  propagates, malformed `from` → `SourceSpecError` propagates, `ResolvedEnv`
  equality) and `tests/integration/test_env_resolution_acceptance.py` (3–5 hermetic
  acceptance tests built from `HookDef` / `check.toml` fixtures, with a `subprocess`
  spy / monkeypatch asserting nothing is spawned — AC-13).

---

## §9 Import direction / no cycle (LOCKED)

- `gatecheck.env` imports: stdlib (`shlex`, `hashlib`, `pathlib`, `dataclasses`,
  `collections.abc`), and — from **other leaves** — `gatecheck.sources`
  (`parse_source`, `resolve_source`, `ProjectSource` / `PyPISource` /
  `SystemSource` / `UnsupportedSource`, and the two source errors propagate through
  it) and `gatecheck.config` (`HookDef`).
- Nothing imports `gatecheck.env` back in this slice (STY-0008 / STY-0009 / the
  runner consume it later). **No cycle.**
- **`gatecheck.sources` is not modified** (`resolve_source` unchanged);
  **`gatecheck.config` is not modified** (no `HookDef.tool` field — design gate).
- Import direction: `config` → `sources` (existing); `registry` → `sources` +
  `config` (existing); `env` → `sources` + `config` (this story). Acyclic.

---

## §10 Explicitly OUT of scope (re-stated)

- **uv-backed venv creation for `pypi:` / `pypi+alias:`** — `uv venv` / `uv pip
  install`, content-addressed cache dirs, `--require-hashes` — **STY-0008.** This
  story routes `pypi` to a deferred `EnvError`; that `match` arm is the single seam
  STY-0008 replaces.
- **Calling `registry.resolve_pypi_source`** — the pinned-dist hand-off is consumed
  in STY-0008, not here.
- **Cache hit/miss tracing / `gatecheck cache why`** — **STY-0009.** This story
  defines the `cache_key` *derivation* only; it stores / explains nothing.
- **Running the executable** — the runner (argv assembly, changed-file passing,
  output streaming, exit codes).
- **Workspace-aware / per-package interpreter selection** — a single
  `workspace_root` is enough now.
- **`cache_root` / uv-path / client constructor parameters** — STY-0008 / STY-0009.
- **Changing `ResolvedEnv` to pydantic** — locked out (§3); it stays a frozen
  dataclass.
- **`HookDef.tool` schema field / any `HookDef` change** — locked out; tool name is
  derived from `hook.run` (design gate).
- **Modifying `resolve_source` / `gatecheck.sources`** — unchanged.

---

## Appendix

- Story:
  `planning/features/FEAT-0003-environments/stories/STY-0007-env-manager-non-venv-path.md`
- Feature: `planning/features/FEAT-0003-environments/feature.md`
- Build charter: `planning/build-plans/0007-charter.md`
- Predecessor architecture documents:
  - `0006-architecture-decision.md` — `RegistryError` shape, injected-seam idiom,
    frozen-model idiom, `__all__` ordering, "does NOT map to `ConfigError`"
    reasoning (mirrored here for `EnvError`).
  - `0005-architecture-decision.md` — `SourceResolutionError` shape, `resolve_source`
    injected `environ` / `workspace_root` seams, `ResolvedTool` model.
  - `0004-architecture-decision.md` — `ParsedSource` union, the four source models,
    import direction.
- Consumed (unchanged) code:
  - `src/gatecheck/sources/parser.py` — `parse_source` (may raise `SourceSpecError`).
  - `src/gatecheck/sources/resolver.py` — `resolve_source(source, tool, *,
    workspace_root=None, environ=None) -> ResolvedTool`; **not modified**.
  - `src/gatecheck/sources/resolved_tool.py` — `ResolvedTool(tool, executable,
    origin)` (the `_cache_key` / `bin_dir` inputs).
  - `src/gatecheck/sources/parsed_source.py` + the four member models — the `match`
    dispatch.
  - `src/gatecheck/sources/source_resolution_error.py` /
    `source_spec_error.py` — the two errors that propagate unwrapped.
  - `src/gatecheck/config/hook_def.py` — `HookDef.id` / `.from_` / `.run`.
- New code (red): `src/gatecheck/env/env_error.py`; build out
  `src/gatecheck/env/manager.py`; edit `src/gatecheck/env/__init__.py`.
- New tests (red): `tests/unit/test_env_manager.py` (currently a skipped scaffold),
  `tests/integration/test_env_resolution_acceptance.py`.
- Docs (updated by TSK-009, not this doc): a "Environments — resolving a hook to an
  executable" subsection in `docs/config/reference.md`.
