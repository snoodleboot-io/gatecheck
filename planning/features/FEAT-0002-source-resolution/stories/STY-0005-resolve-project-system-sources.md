---
id: STY-0005
title: Resolve `from = "project"` and `from = "system"` sources to concrete executables
status: Draft
owner: TBD
date: 2026-07-05
feature: FEAT-0002
prd: PRD-0001 § Scope — Sources (Environments boundary)
adrs: [ADR-0001]
---

# STY-0005: Resolve `from = "project"` and `from = "system"` sources to concrete executables

## As a / I want / So that

As a **gatecheck developer**, I want **a `resolve_source(source, tool)` function
that turns the two non-network `ParsedSource` kinds — `SystemSource` and
`ProjectSource` — into a concrete, absolute executable path** so that **the
runner can invoke a hook's command without re-deriving where the binary lives,
and a missing tool produces a clear "not found on PATH / not in project venv"
error instead of an opaque `FileNotFoundError` when the subprocess is spawned**.

## Scope

STY-0004 gave a hook's `from` string *meaning* — `parse_source` classifies it
into a typed `ParsedSource` union (`PyPISource | ProjectSource | SystemSource |
UnsupportedSource`). This story gives the two **non-network** kinds *location*:
it resolves them to an actual executable on this machine — **filesystem lookup
only. NO network, NO venv creation, NO subprocess execution.** It resolves what
already exists; it never builds an environment.

- `SystemSource` → find `tool` on `PATH` (à la `shutil.which`); error clearly if
  absent.
- `ProjectSource` → locate `tool` inside the project's own already-existing
  environment (active `VIRTUAL_ENV`, else a discovered `<workspace_root>/.venv`);
  error clearly if absent. **No venv is created** — that is the Environments
  feature (PRD-0001 § Scope — Environments).

Explicitly **out of scope**:
- `PyPISource` — network/registry resolution + venv creation is STY-0006 /
  Environments. `resolve_source` rejects it with a typed error rather than
  reaching for the network.
- `UnsupportedSource` — `local:` / `git:` / `docker:` remain recognized-but-
  unsupported; `resolve_source` rejects them with a typed error.
- Tokenizing `HookDef.run` into a command + args, and actually running the
  executable — the runner's job (PRD-0001 § Scope — Runner).
- Workspace discovery (walking up for `check.toml` / `pyproject.toml`) — the
  Workspace feature. STY-0005 takes `workspace_root` as an input (default:
  `Path.cwd()`).
- Windows `Scripts\` layout — POSIX `bin/` first per PRD-0001 § Open questions
  (Windows is a fast-follower); documented as a locked-later decision, not built
  here.

### Where the new code lives — **recommendation: `gatecheck.sources` (a new `resolver.py`)**

The resolver lands in the existing leaf package `src/gatecheck/sources/`,
alongside `parser.py`, **not** in `gatecheck.env`.

Rationale:
- **It consumes and extends `sources`' own types.** `resolve_source` takes a
  `ParsedSource` (defined here) and produces a concrete executable with no notion
  of a *cached environment*. It is the natural second half of the parse→resolve
  slice STY-0004 started, in the same package. `parse_source` → `resolve_source`
  reads as one story arc.
- **It stays a pure, dependency-light leaf.** `gatecheck.sources` imports nothing
  from `gatecheck.config` or `gatecheck.env`; keeping the resolver here preserves
  that. It needs only `os` / `shutil` / `pathlib`.
- **`gatecheck.env` is a different abstraction.** `EnvManager.resolve(hook) ->
  ResolvedEnv(bin_dir, cache_key)` is about **uv-backed venv creation and
  caching** — the Environments feature. Its return type is an *environment* (a
  bin dir + a cache key), not a single located binary. STY-0005 produces no cache
  key and creates no env, so it does not fit that contract. Later, `EnvManager`
  (or the runner) will **delegate** the `project`/`system` kinds to
  `sources.resolve_source` and own only the `pypi:` venv path itself.
- **The `env` package is currently uncommitted/gitignored** (see Notes). Landing
  the resolver there would force this story to also un-ignore, commit, and
  lint-clean the whole Environments scaffold — unrelated scope. Keeping the
  resolver in `sources` avoids that coupling entirely.

Files (one class/function-group per file per core conventions):

| File | Single responsibility |
|---|---|
| `src/gatecheck/sources/resolved_tool.py` | `ResolvedTool` frozen pydantic model. |
| `src/gatecheck/sources/source_resolution_error.py` | `SourceResolutionError(ValueError)`. |
| `src/gatecheck/sources/resolver.py` | `resolve_source(...) -> ResolvedTool` + private helpers. No class. |
| `src/gatecheck/sources/__init__.py` | Facade — extend imports + `__all__` with the three new symbols. |

### Input / output contract (describe — do not implement)

```python
# resolver.py
def resolve_source(
    source: ParsedSource,
    tool: str,
    *,
    workspace_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedTool: ...
```

- **`source`** — the classified `ParsedSource` from `parse_source(hook.from_)`.
  Only `SystemSource` / `ProjectSource` resolve; `PyPISource` /
  `UnsupportedSource` raise `SourceResolutionError` (they are handled elsewhere /
  not yet supported).
- **`tool`** — the executable/command name to locate (e.g. `"ruff"`). It is the
  first shell token of `HookDef.run` (`run = "ruff check"` → `tool = "ruff"`).
  STY-0005's resolver takes `tool` **explicitly as a string** and does not itself
  tokenize `run` — that is the runner/caller's concern (or a thin future helper),
  keeping the resolver pure and trivially testable. `tool` must be a bare name,
  not a path.
- **`workspace_root`** — the project root under which `.venv` is discovered for
  `ProjectSource`. Defaults to `Path.cwd()`. Real workspace discovery is out of
  scope (Workspace feature).
- **`environ`** — the environment mapping read for `PATH` (system) and
  `VIRTUAL_ENV` (project). Defaults to `os.environ`. Injectable so tests are
  hermetic and the function stays a pure function of its inputs.

**Returns** a `ResolvedTool` (frozen pydantic `BaseModel`, mirroring the STY-0004
source models — `model_config = ConfigDict(frozen=True, extra="forbid")`):

- `tool: str` — the requested command name (echoed back).
- `executable: Path` — the **absolute** path to the resolved executable.
- `origin: Literal["project", "system"]` — which rule produced the result, for
  runner/cache explainability (PRD-0001 § Goal 5).

`executable` is always absolute (the resolver applies `Path(...).resolve()` to
whatever `shutil.which` / the `.venv` scan returns).

### Error type / behavior

A dedicated `SourceResolutionError(ValueError)` in
`src/gatecheck/sources/source_resolution_error.py`, mirroring `SourceSpecError`'s
shape (subclasses `ValueError`; carries structured fields; location-free):

```python
class SourceResolutionError(ValueError):
    tool: str
    kind: str        # the source's `.kind` — "system" | "project" | "pypi" | "unsupported"
    reason: str
    def __init__(self, tool: str, kind: str, reason: str) -> None:
        self.tool = tool
        self.kind = kind
        self.reason = reason
        super().__init__(f"cannot resolve '{tool}' from {kind} source: {reason}")
```

Message form: `cannot resolve '<tool>' from <kind> source: <reason>` — e.g.
`cannot resolve 'ruff' from system source: not found on PATH`.

Mapping to `ConfigError` — **it does not map.** Unlike `SourceSpecError` (a
*syntax* error in `check.toml`, knowable at load time and wrapped by the config
layer with `path:line:col`), a resolution failure is a **runtime/environment**
condition: the `from` and `run` are syntactically valid, but the tool is absent
*on this machine right now*. It has no `check.toml:line:col` meaning. Therefore:

- `SourceResolutionError` is **not** raised from `load_config` and is **not**
  wrapped as `ConfigError`. Loading a config whose tool happens to be absent
  still succeeds.
- It surfaces at **resolve/run time** (the runner catches it and reports the
  hook that failed to resolve). The runner may attach the offending hook id for
  context — analogous to STY-0004's `(hook: …)` suffix — but STY-0005's resolver
  itself stays hook-unaware and location-free.

### Resolution rules (precise, deterministic)

**`SystemSource`** — resolve `tool` against `PATH`:
1. Read `PATH` from `environ` (default `os.environ`).
2. `located = shutil.which(tool, path=environ.get("PATH"))` — first directory in
   `PATH` order containing an executable match wins (standard `which` semantics).
3. If `located is None` → `SourceResolutionError(tool, "system", "not found on
   PATH")`.
4. Else → `ResolvedTool(tool=tool, executable=Path(located).resolve(),
   origin="system")`.

**`ProjectSource`** — locate `tool` in the project's own existing environment, in
this **precedence order** (first existing + executable candidate wins):
1. **Active venv:** if `environ.get("VIRTUAL_ENV")` is set and non-empty →
   candidate `Path(VIRTUAL_ENV) / "bin" / tool`.
2. **Discovered project venv:** candidate `(workspace_root or Path.cwd()) /
   ".venv" / "bin" / tool`.

A candidate qualifies only if it **exists**, is a **regular file** (following
symlinks), and is **executable** (`os.access(path, os.X_OK)`). The first
qualifying candidate → `ResolvedTool(tool=tool,
executable=candidate.resolve(), origin="project")`. If neither qualifies →
`SourceResolutionError(tool, "project", "not found in project environment
(checked $VIRTUAL_ENV/bin and <workspace_root>/.venv/bin)")`. A missing `.venv`
is a not-found error, never a trigger to create one.

**Determinism / purity:** given the same `(source, tool, PATH, VIRTUAL_ENV,
workspace_root, filesystem state)`, `resolve_source` returns an equal
`ResolvedTool` (or raises the same error) on every call. It performs **no
network, no subprocess, no writes** — only `PATH`/dir reads and `os.access`
checks. Repeated calls do not mutate anything.

**`PyPISource` / `UnsupportedSource`:** `resolve_source` raises
`SourceResolutionError` immediately — for `pypi`, reason `pypi source resolution
is delegated to Environments (STY-0006), not handled here`; for `unsupported`,
reason `'<scheme>' sources are not supported`. Single error type; the caller can
branch on `.kind`.

## Tasks

- [ ] TSK-001: Add `src/gatecheck/sources/resolved_tool.py` — `ResolvedTool`
  frozen pydantic model (`tool: str`, `executable: Path`,
  `origin: Literal["project", "system"]`; `ConfigDict(frozen=True,
  extra="forbid")`).
- [ ] TSK-002: Add `src/gatecheck/sources/source_resolution_error.py` —
  `SourceResolutionError(ValueError)` with structured `tool` / `kind` / `reason`
  and the `cannot resolve '<tool>' from <kind> source: <reason>` message.
- [ ] TSK-003: Implement `resolve_source(source, tool, *, workspace_root=None,
  environ=None) -> ResolvedTool` in `src/gatecheck/sources/resolver.py`:
  `match` on the source kind; system (`shutil.which`) and project
  (`VIRTUAL_ENV` → `.venv` precedence, exists+file+executable) rules; absolutize
  the result; reject `pypi` / `unsupported` with `SourceResolutionError`.
- [ ] TSK-004: Extend `src/gatecheck/sources/__init__.py` facade + `__all__` with
  `resolve_source`, `ResolvedTool`, `SourceResolutionError` (keep the existing
  alphabetical ordering convention).
- [ ] TSK-005: Write `tests/unit/test_source_resolve.py` (≥ 12 tests, hermetic
  via `tmp_path` + monkeypatched `environ`, no network): system found / system
  absent; project via `VIRTUAL_ENV`; project via `<root>/.venv`; precedence
  (VIRTUAL_ENV wins over `.venv`); project not-found; non-executable candidate
  skipped; absolute-path guarantee; `pypi` rejected; `unsupported` rejected;
  determinism (two calls equal); error message format.
- [ ] TSK-006: Write `tests/integration/test_source_resolution_acceptance.py`
  (3–5 tests): resolve a real `system` tool end-to-end (e.g. the current
  interpreter's basename on `PATH`) and assert the returned `executable` exists
  and is absolute; a bogus tool raises `SourceResolutionError` naming the tool;
  `load_config` of a config whose tool is absent still succeeds (proves no
  `ConfigError` mapping).
- [ ] TSK-007: Add a "Resolving `project` / `system` sources" subsection to
  `docs/config/reference.md § Source spec syntax` documenting `resolve_source`,
  `ResolvedTool`, the discovery/precedence rules, and the "not found" error
  (and that resolution failure is a runtime, not a config, error).
- [ ] TSK-008: **Raise a separate chore** (do NOT bundle into STY-0005) to
  un-ignore, commit, and lint-clean the `src/gatecheck/env/` package — fix
  `.gitignore` (anchor `/env/` or add `!src/gatecheck/env/`) and make the package
  `ruff` / `mypy --strict` clean. See Notes for why this is split out.

## Acceptance criteria

- [ ] AC-1: `resolve_source(SystemSource(), tool)` for a tool present on `PATH`
  returns a `ResolvedTool` whose `executable` equals
  `Path(shutil.which(tool)).resolve()`, is absolute, exists, and whose
  `origin == "system"`.
- [ ] AC-2: `resolve_source(SystemSource(), tool)` for a tool **absent** from
  `PATH` raises `SourceResolutionError` whose `reason` is `not found on PATH`.
- [ ] AC-3: `resolve_source(ProjectSource(), tool)` with `VIRTUAL_ENV` pointing at
  a dir containing an executable `bin/<tool>` resolves to
  `<VIRTUAL_ENV>/bin/<tool>` (absolute) with `origin == "project"`.
- [ ] AC-4: `resolve_source(ProjectSource(), tool, workspace_root=root)` with no
  `VIRTUAL_ENV` and an executable `<root>/.venv/bin/<tool>` resolves there
  (absolute, `origin == "project"`).
- [ ] AC-5: When both an active `VIRTUAL_ENV` and `<root>/.venv` contain the tool,
  the `VIRTUAL_ENV` candidate wins (documented precedence).
- [ ] AC-6: `resolve_source(ProjectSource(), tool)` with the tool in neither
  location raises `SourceResolutionError` whose `reason` names the project
  environment (`$VIRTUAL_ENV/bin` and `<workspace_root>/.venv/bin`).
- [ ] AC-7: A candidate path that exists but is **not executable** does not
  qualify (project resolution skips it and reports not-found rather than
  returning a non-executable path).
- [ ] AC-8: `resolve_source(PyPISource(requirement="ruff"), "ruff")` and
  `resolve_source(UnsupportedSource(scheme="git"), "x")` each raise
  `SourceResolutionError` (never a network call, never a crash).
- [ ] AC-9: `resolve_source` performs no network, no subprocess, and no
  filesystem writes — a missing `.venv` is **not** created (verifiable by
  inspection / mock-free hermetic tests over `tmp_path`).
- [ ] AC-10: Resolution is deterministic — for fixed
  `(source, tool, PATH, VIRTUAL_ENV, workspace_root, fs)`, two calls return equal
  `ResolvedTool` values (or raise the same error).
- [ ] AC-11: `ResolvedTool.executable` is always an absolute `Path`.
- [ ] AC-12: `SourceResolutionError` subclasses `ValueError`; its message has the
  form `cannot resolve '<tool>' from <kind> source: <reason>`.
- [ ] AC-13: A resolution failure does **not** surface as `ConfigError` and is
  **not** raised from `load_config` — loading a config whose tool is absent
  succeeds; the error only appears when `resolve_source` is called.
- [ ] AC-14: `from gatecheck.sources import resolve_source, ResolvedTool,
  SourceResolutionError` works.
- [ ] AC-15: `mypy --strict src/gatecheck/sources/` passes with no new errors;
  the `match` over `ParsedSource` narrows the `SystemSource` / `ProjectSource`
  cases cleanly.
- [ ] AC-16: No new runtime dependencies added (`os`, `shutil`, `pathlib`,
  `typing` only, plus existing `pydantic`).

## Notes

- **Resolver location (architect to confirm):** `gatecheck.sources.resolver` is
  recommended over `gatecheck.env` — see § Where the new code lives. If the
  architect instead places it in `gatecheck.env`, the `.gitignore` un-ignore
  (TSK-008) **must** move into this story, since the resolver could not otherwise
  be committed.
- **`.gitignore` / env-package bundling (recommendation: SPLIT):** the bare
  `env/` line in `.gitignore` (intended for virtualenvs) also matches
  `src/gatecheck/env/`, so that package (`manager.py`, `__init__.py`) is silently
  uncommitted. Because STY-0005's resolver lands in `gatecheck.sources`, this
  story does **not** need the env package committed, so the un-ignore is kept out
  of STY-0005 and raised as its own chore (TSK-008). Rationale: bundling an
  un-ignore + making the entire Environments scaffold `ruff` / `mypy --strict`
  clean is unrelated scope that would bloat a focused resolution PR and couple it
  to a feature (Environments) that is not yet being built. Flag: once un-ignored,
  the env package is subject to `ruff` / `mypy --strict`, so the chore must clean
  it (it is not currently gated). Note also that BUILD-0004 already corrected
  `env/manager.py`'s import from `gatecheck.config.schema` to
  `gatecheck.config.hook_def` in the working copy — but because the package is
  gitignored, that fix is uncommitted and invisible to git; the chore is what
  actually lands it.
- **Tool name derivation:** `tool` is the first shell token of `HookDef.run`.
  STY-0005 takes `tool` as an explicit argument and does **not** tokenize `run` —
  that stays with the runner (or a later thin helper) so the resolver is pure.
- **Windows:** POSIX `bin/` only in v1 (PRD-0001 § Open questions). The `Scripts\`
  layout and `.exe`/`PATHEXT` handling are a documented fast-follower, not built
  here; the architect locks whether `ResolvedTool.origin` / the candidate list
  gains a Windows branch later.
- **Architect to lock:** `ResolvedTool` as frozen pydantic model vs frozen
  dataclass (recommend pydantic for consistency with the STY-0004 source models,
  though it carries a `Path` rather than pure strings); the exact `reason`
  strings for each error branch (mirror STY-0004's LOCKED message table); and
  whether `origin`/explainability metadata belongs on `ResolvedTool` now or waits
  for the Cache feature.
- **Downstream:** the Environments feature's `EnvManager.resolve(hook)` will
  delegate `project`/`system` kinds to `resolve_source` and own only the `pypi:`
  venv-creation path — this story defines the typed hand-off point.
