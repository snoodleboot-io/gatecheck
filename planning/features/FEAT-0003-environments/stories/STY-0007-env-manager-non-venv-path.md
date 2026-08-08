---
id: STY-0007
title: EnvManager skeleton + the non-venv path (project / system → ResolvedEnv); pypi deferred
status: Draft
owner: TBD
date: 2026-07-05
feature: FEAT-0003
prd: PRD-0001 § Scope — Environments
adrs: [ADR-0001]
---

# STY-0007: `EnvManager` skeleton + the non-venv path (`project` / `system` → `ResolvedEnv`); `pypi` deferred

## As a / I want / So that

As a **hooksmith developer**, I want **`EnvManager.resolve(hook)` to turn a
`HookDef` whose `from` is `project` or `system` into a `ResolvedEnv(bin_dir,
cache_key)` by classifying the spec (`parse_source`) and locating the tool named
by `hook.run` (`resolve_source`), with a deterministic `cache_key`** so that
**the runner has one contract to get an executable environment for a hook, the
non-network kinds work end-to-end today with no subprocess or network, and the
`pypi` / uv-backed slice (STY-0008) can drop into a well-defined branch without
reshaping the contract**.

## Scope

FEAT-0002 finished the *description* of a source: `parse_source(hook.from_)`
classifies the `from` string into a `ParsedSource`, and
`resolve_source(source, tool, …)` locates the two **non-network** kinds
(`ProjectSource`, `SystemSource`) as a concrete `ResolvedTool` (absolute
executable + `origin`). `resolve_source` deliberately **rejects** `PyPISource`
with `SourceResolutionError("pypi source resolution is delegated to Environments
(STY-0006), not handled here")`.

This story builds out the existing `EnvManager` stub
(`src/hooksmith/env/manager.py`, currently `resolve` raises `NotImplementedError`)
to light up the **non-venv path only**:

- Establish the `EnvManager` contract, constructor state, the `ResolvedEnv`
  value, and the **`cache_key` scheme** — the shape STY-0008 (uv venvs) and
  STY-0009 (cache explainability) build on.
- Dispatch `project` / `system` through `resolve_source` and build a
  `ResolvedEnv` from the resolved executable.
- **Defer `pypi`** with a clear, typed "not yet implemented (STY-0008)" error —
  no `uv`, no subprocess, no network, no filesystem writes.

Keeping this slice **pure and hermetic** (a deterministic function of `hook`,
`workspace_root`, `environ`, and filesystem state — exactly `resolve_source`'s
contract) means it is fully unit-testable with no subprocess/network and lets the
runner integrate against the real contract before uv work lands.

Explicitly **out of scope** (deferred to later stories in FEAT-0003):

- **uv-backed venv creation for `pypi:` / `pypi+alias:`.** Shelling out to `uv
  venv` / `uv pip install`, content-addressed cache dirs, `--require-hashes` —
  **STY-0008**. This story only *routes* `pypi` to a deferred error.
- **Calling `registry.resolve_pypi_source`.** The pinned-dist hand-off is consumed
  in STY-0008, not here.
- **Cache hit/miss tracing and `hooksmith cache why`** (PRD-0001 § Scope — Cache)
  — **STY-0009**. This story defines the `cache_key` *derivation* but stores /
  explains nothing.
- **Running the executable** — the runner's job.
- **Workspace-aware per-package interpreter selection** — layers on later; a single
  `workspace_root` is enough now.

## Behavior — `EnvManager.resolve(hook)`

`resolve` is a pure function of `(hook, self._workspace_root, self._environ,
filesystem state)`. Steps:

1. **Classify the source.** `source = parse_source(hook.from_)` →
   `ParsedSource`. (`hook.from_` is validated non-empty by the config loader, but
   `parse_source` may still raise `SourceSpecError` for a malformed spec — see
   § Error behavior.)
2. **Derive the tool name** from `hook.run` (see § Tool-name derivation).
3. **Dispatch on the `ParsedSource` kind** (`match`, mirroring `resolve_source`):
   - `SystemSource()` / `ProjectSource()` →
     `tool_ = resolve_source(source, tool, workspace_root=self._workspace_root,
     environ=self._environ)` → `ResolvedTool`. Build and return
     `ResolvedEnv(bin_dir=tool_.executable.parent, cache_key=_cache_key(tool_))`.
   - `PyPISource()` → raise `EnvError` (deferred — see § pypi handling). This
     branch is where STY-0008 will instead call `registry.resolve_pypi_source` +
     `uv`.
   - `UnsupportedSource(scheme=…)` → raise `EnvError` (unsupported kind — see
     § Error behavior).

`bin_dir` is the **parent directory of the resolved executable**
(`ResolvedTool.executable` is already an absolute, `.resolve()`-d path), i.e. the
directory the runner adds to `PATH` / runs the command from. For `project`/`system`
this is an existing directory (`.venv/bin`, or the dir the binary lives in on
`PATH`); no directory is created.

### Tool-name derivation (the rule)

The tool is the **first shell token of `hook.run`**, obtained with
`shlex.split(hook.run)` and taking element `[0]`:

- `shlex.split` (POSIX mode) is used rather than `str.split()` so a quoted or
  escaped program name is handled correctly and consistently with how the runner
  will eventually tokenize the command.
- If `shlex.split(hook.run)` is **empty** (e.g. `run` is only whitespace — `run`
  has `min_length=1` but a single space still passes that check) or `shlex.split`
  raises `ValueError` (unbalanced quotes), raise `EnvError` naming the hook and the
  offending `run` string ("cannot derive a tool name from run = …").
- Only the **first token** is used to locate the executable; the remaining tokens
  (arguments) are the runner's concern, not the environment's.

> **Architect to lock (biggest open question):** the tool-name rule. `shlex.split(
> hook.run)[0]` is recommended, but alternatives are (a) plain `hook.run.split()[0]`
> (no quote handling) or (b) a future explicit `hook.tool` field on `HookDef` so
> the command and the executable name are decoupled. The `cache_key` inputs (below)
> depend on this being stable.

### `cache_key` derivation (deterministic)

For the non-venv kinds the "environment" is fully identified by the **resolved
executable** and which rule produced it. The key is a SHA-256 hex digest over a
versioned, newline-joined material string:

```
_CACHE_KEY_SCHEME = "env-v1"
material = "\n".join([_CACHE_KEY_SCHEME, resolved.origin, str(resolved.executable)])
cache_key = hashlib.sha256(material.encode("utf-8")).hexdigest()   # 64-char hex
```

- **Inputs:** the scheme tag (`"env-v1"`, so the format can evolve), the
  `ResolvedTool.origin` (`"project"` / `"system"` — so the same binary reached two
  ways keys distinctly), and the absolute resolved executable path.
- **Determinism:** `resolve_source` returns a `Path(...).resolve()`-d absolute
  path that is a deterministic function of `(source, tool, PATH/VIRTUAL_ENV,
  workspace_root, filesystem state)`; hashing it is therefore deterministic — two
  calls with the same inputs and filesystem state yield an identical `cache_key`
  (and equal `ResolvedEnv`, since `ResolvedEnv` is a frozen dataclass).
- **Forward-compatibility:** STY-0008's uv venvs derive their key from the same
  scheme tag but over the pinned `name`+`version`+`index_url` (content-addressing
  the venv). The `env-vN` prefix keeps the two derivations in one namespace and
  lets STY-0009 explain either. Keeping the exact key material in one private
  `_cache_key(...)` helper localizes the decision.

> **Architect to lock:** the precise `cache_key` inputs (scheme tag; whether to
> include `origin`; full 64-char digest vs. a truncated prefix). Recorded above as
> the story's recommendation; STY-0009 depends on this being stable and explainable.

### `pypi` handling in THIS story (deferred)

A `PyPISource` (`pypi:` / `pypi+alias:`) is **not** resolved here — it needs the
network resolver (`registry.resolve_pypi_source`) and a `uv` subprocess, both
STY-0008. This story raises a typed, actionable error rather than calling
`resolve_source` (whose `PyPISource` branch already points at Environments):

- Raise **`EnvError`** with a reason like `"pypi environments are not yet
  implemented (deferred to STY-0008)"`, naming the hook id.
- This is the exact branch STY-0008 replaces with the resolve-and-build logic, so
  the deferral is a single, clearly-marked seam.

### Constructor state (minimal, forward-compatible)

`EnvManager(workspace_root: Path | None = None, environ: Mapping[str, str] | None
= None)`:

- `workspace_root` / `environ` are stored and **passed straight through to
  `resolve_source`**, mirroring `resolve_source`'s own injectable seams (defaults
  resolved lazily: `None` → `Path.cwd()` / `os.environ` — done by `resolve_source`,
  so `EnvManager` can hold `None` and forward it). This keeps the class a pure,
  deterministic function of its injected inputs for hermetic tests.
- No `cache_root` / uv-path / client parameters are added now — those belong to
  STY-0008/STY-0009. Adding only what the non-venv path needs keeps the surface
  minimal while leaving the constructor open for extension (the runner constructs
  `EnvManager` once and reuses it).

### Error behavior

Reuse FEAT-0002's typed errors where they already fit; add a feature-local
`EnvError` only for the cases `EnvManager` itself owns:

| Condition | Error | Wrapped by EnvManager? |
|---|---|---|
| `hook.from_` is a malformed spec | `SourceSpecError` (from `parse_source`) | **No** — propagates unchanged (it is a config-syntax error, already typed). |
| `project`/`system` tool not found (PATH / venv) | `SourceResolutionError` (from `resolve_source`) | **No** — propagates unchanged (already a clear runtime error carrying `tool`/`kind`/`reason`). |
| `run` yields no tool name / unbalanced quotes | `EnvError` | raised by `EnvManager`. |
| `pypi:` / `pypi+alias:` | `EnvError` (deferred to STY-0008) | raised by `EnvManager`. |
| `local:` / `git:` / `docker:` (`UnsupportedSource`) | `EnvError` (unsupported kind) | raised by `EnvManager`. |

**Decision — EnvManager does not wrap `SourceResolutionError` / `SourceSpecError`.**
They are already typed `ValueError` subclasses with good messages and structured
fields; re-wrapping would hide `tool`/`kind`/`reason`. `EnvError` is introduced only
for env-management-domain failures (unresolvable tool name, deferred/unsupported
kinds). `EnvError` subclasses `ValueError`, mirroring `SourceResolutionError` /
`RegistryError` (structured fields + a `cannot resolve environment for hook
'<id>': <reason>` message). Like those, it is a **runtime** error and does **not**
map to `ConfigError` / carry a `line:col`.

> **Architect to lock:** whether `EnvManager` should instead *wrap* every failure in
> `EnvError` (uniform single error domain from the env layer, chaining the cause via
> `raise EnvError(...) from err`) versus letting the FEAT-0002 errors propagate
> (recommended, less lossy). Recorded as a recommendation, not settled.

## Files (one class/function-group per file per core conventions)

| File | Single responsibility |
|---|---|
| `src/hooksmith/env/manager.py` | Build out `EnvManager` (constructor state + `resolve` dispatch + `_cache_key`); `ResolvedEnv` stays here. (Existing file.) |
| `src/hooksmith/env/env_error.py` | `EnvError(ValueError)` with structured `hook_id` / `reason` and the `cannot resolve environment for hook '<id>': <reason>` message. (New.) |
| `src/hooksmith/env/__init__.py` | Facade — export `EnvManager`, `ResolvedEnv`, `EnvError`; set `__all__` (alphabetical). (Existing file — extend.) |

## Tasks

- [ ] TSK-001: Add `src/hooksmith/env/env_error.py` — `EnvError(ValueError)` with
  structured `hook_id` / `reason` fields and message `cannot resolve environment for
  hook '<hook_id>': <reason>`, mirroring `SourceResolutionError`'s shape.
- [ ] TSK-002: Build out `EnvManager` in `src/hooksmith/env/manager.py` — add
  `__init__(self, workspace_root: Path | None = None, environ: Mapping[str, str] |
  None = None)` storing both; keep the `ResolvedEnv` dataclass.
- [ ] TSK-003: Implement the tool-name derivation helper (`shlex.split(hook.run)[0]`;
  empty / `ValueError` → `EnvError`).
- [ ] TSK-004: Implement `resolve(self, hook: HookDef) -> ResolvedEnv` — call
  `parse_source`, derive the tool, `match` the `ParsedSource`: `System`/`Project` →
  `resolve_source(...)` → `ResolvedEnv(bin_dir=executable.parent, cache_key=...)`;
  `PyPISource` → `EnvError` (deferred to STY-0008); `UnsupportedSource` → `EnvError`
  (unsupported kind).
- [ ] TSK-005: Implement the private `_cache_key(resolved: ResolvedTool) -> str`
  helper — `sha256("env-v1\n" + origin + "\n" + str(executable))` hexdigest; define
  `_CACHE_KEY_SCHEME = "env-v1"`.
- [ ] TSK-006: Update `src/hooksmith/env/__init__.py` to export `EnvError` alongside
  `EnvManager` / `ResolvedEnv` (`__all__`, alphabetical).
- [ ] TSK-007: Write `tests/unit/test_env_manager.py` (hermetic — no subprocess, no
  network; inject `workspace_root` + `environ`, use `tmp_path` fake venv / fake
  `PATH` dir): `system` resolve → `ResolvedEnv` with `bin_dir` = binary's parent;
  `project` resolve via fake `.venv/bin` and via `$VIRTUAL_ENV`; `cache_key` is a
  64-char hex digest; `cache_key` deterministic across two calls; `project` vs
  `system` for the same path key **differently**; `pypi:` and `pypi+alias:` →
  `EnvError` (deferred); `local:`/`git:`/`docker:` → `EnvError` (unsupported);
  whitespace-only `run` → `EnvError`; unbalanced-quote `run` → `EnvError`;
  tool-not-found → `SourceResolutionError` propagates; malformed `from` →
  `SourceSpecError` propagates; `ResolvedEnv` equality (frozen dataclass).
- [ ] TSK-008: Write `tests/integration/test_env_resolution_acceptance.py` (3–5
  tests, hermetic): a `system` hook and a `project` hook (built from a `HookDef` /
  `check.toml` fixture) each resolve to a `ResolvedEnv` whose `bin_dir` contains the
  executable; a `pypi:` hook raises `EnvError` mentioning STY-0008; no subprocess is
  spawned (assert via a `subprocess` spy / monkeypatch that raises if called).
- [ ] TSK-009: Add an "Environments — resolving a hook to an executable" subsection
  to `docs/config/reference.md` documenting `EnvManager.resolve(hook) -> ResolvedEnv`,
  the tool-name rule, the `cache_key` scheme, and that `pypi` is uv-backed
  (STY-0008) while `project`/`system` reuse existing binaries.

## Acceptance criteria

- [ ] AC-1: `EnvManager().resolve(hook)` for a `from = "system"` hook whose `run`
  names a tool on `PATH` returns `ResolvedEnv(bin_dir=<tool's parent dir>,
  cache_key=<hex>)`; `bin_dir` contains that executable.
- [ ] AC-2: `EnvManager(workspace_root=root).resolve(hook)` for `from = "project"`
  resolves the tool from `<root>/.venv/bin` (and from `$VIRTUAL_ENV/bin` when
  `environ` supplies it), with `bin_dir` = the executable's parent.
- [ ] AC-3: The tool name is the first `shlex.split(hook.run)` token; extra argv
  tokens are ignored for resolution.
- [ ] AC-4: `cache_key` is a 64-char lowercase hex SHA-256 digest over
  `"env-v1\n<origin>\n<absolute executable path>"`.
- [ ] AC-5: `cache_key` is deterministic — two `resolve` calls with the same hook,
  `workspace_root`, `environ`, and filesystem state return an equal `cache_key` and
  an equal `ResolvedEnv`.
- [ ] AC-6: The same executable reached via `project` vs `system` produces
  **different** `cache_key`s (the `origin` is part of the material).
- [ ] AC-7: `from = "pypi:ruff>=0.4"` and `from = "pypi+internal:x==1"` each raise
  `EnvError` whose message names the hook id and states the `pypi` path is deferred
  to STY-0008 — **no** `resolve_source` call, **no** subprocess, **no** network.
- [ ] AC-8: `from = "local:…"` / `git:` / `docker:` (`UnsupportedSource`) raises
  `EnvError` (unsupported kind).
- [ ] AC-9: A `run` that yields no tokens (whitespace-only) or has unbalanced quotes
  raises `EnvError` naming the hook and the `run` string.
- [ ] AC-10: A `project`/`system` tool that cannot be located propagates
  `SourceResolutionError` (from `resolve_source`) **unchanged** — `EnvManager` does
  not wrap it.
- [ ] AC-11: A malformed `from` spec propagates `SourceSpecError` (from
  `parse_source`) unchanged.
- [ ] AC-12: `EnvError` subclasses `ValueError`, carries `hook_id` / `reason`, and
  has the message form `cannot resolve environment for hook '<id>': <reason>`; it is
  never surfaced as `ConfigError` and carries no `line:col`.
- [ ] AC-13: The entire story runs with **no subprocess and no network** — the unit
  and integration suites are hermetic (a `subprocess` spy asserts nothing is
  spawned); `resolve` is a deterministic function of its injected inputs.
- [ ] AC-14: `from hooksmith.env import EnvManager, ResolvedEnv, EnvError` works.
- [ ] AC-15: `mypy --strict src/hooksmith/env/` passes with no new errors; the
  `match` over `ParsedSource` is exhaustive.
- [ ] AC-16: `EnvManager.resolve` never creates, writes, or mutates any directory —
  `bin_dir` is always an already-existing directory for the resolved kinds.

## Notes

- **Reuses, adds nothing external.** No new runtime dependency and no external
  binary in this slice — `shlex` / `hashlib` are stdlib; `uv` enters in STY-0008.
- **Contract stability.** `ResolvedEnv(bin_dir, cache_key)` is kept exactly as the
  existing stub defines it so STY-0008/STY-0009 and the runner build on an unchanged
  shape; the `pypi` branch is the only planned point of change.
- **Biggest design question for the architect:** the **tool-name derivation** (first
  `shlex.split` token vs. `str.split` vs. a future explicit `hook.tool` field) —
  because the `cache_key` and the runner's argv both depend on it. Secondary: the
  exact `cache_key` inputs / scheme tag, which STY-0009's explainability builds on.
