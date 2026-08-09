---
id: BUILD-0005-CHARTER
title: Build charter for STY-0005 (resolve project + system sources)
parent: BUILD-0005
target_story: STY-0005
status: Locked
date: 2026-07-05
---

# BUILD-0005 Charter — STY-0005 (Resolve `project` / `system` sources to executables)

## Goal

Give the two **non-network** `ParsedSource` kinds — `SystemSource` and
`ProjectSource` — a *location*. Deliver a pure, synchronous
`resolve_source(source, tool, *, workspace_root=None, environ=None) ->
ResolvedTool` function in the existing leaf package `src/hooksmith/sources/`
that turns those kinds into a concrete, **absolute** executable path the runner
can invoke without re-deriving where the binary lives. A missing tool raises a
dedicated `SourceResolutionError(ValueError)` with a clear "not found on PATH /
not in project environment" message instead of an opaque `FileNotFoundError` at
subprocess spawn.

This is the second vertical slice of FEAT-0002 — the natural second half of the
STY-0004 parse→resolve arc (`parse_source` → `resolve_source`). **Filesystem
lookup only: NO network, NO venv creation, NO subprocess execution.** It
resolves what already exists; it never builds an environment. See
[STY-0005](../features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md),
[FEAT-0002](../features/FEAT-0002-source-resolution/feature.md),
[PRD-0001 § Scope — Sources](../prd/0001-hooksmith.md#scope), and
[ADR-0001](../adr/0001-python-host-rust-core.md).

## In-scope for this build

Single-PR vertical slice. All new code lands in the existing package
`src/hooksmith/sources/` (one class/function-group per file, per core
conventions):

- `src/hooksmith/sources/resolved_tool.py` — `ResolvedTool` frozen pydantic
  model (`tool: str`, `executable: Path`, `origin: Literal["project",
  "system"]`; `ConfigDict(frozen=True, extra="forbid")`).
- `src/hooksmith/sources/source_resolution_error.py` —
  `SourceResolutionError(ValueError)` with structured `tool` / `kind` / `reason`
  and the `cannot resolve '<tool>' from <kind> source: <reason>` message.
- `src/hooksmith/sources/resolver.py` — `resolve_source(...) -> ResolvedTool`
  plus private helpers (no class); a `match` over `ParsedSource` with the
  `SystemSource` (`shutil.which`) and `ProjectSource` (`VIRTUAL_ENV` → `.venv`
  precedence, exists + regular-file + executable) rules; reject `PyPISource` /
  `UnsupportedSource` with `SourceResolutionError`.
- `src/hooksmith/sources/__init__.py` — extend the facade imports + `__all__`
  with `ResolvedTool`, `SourceResolutionError`, `resolve_source` (keep the
  existing alphabetical, uppercase-before-lowercase ordering).
- Unit tests in `tests/unit/test_source_resolve.py` (≥ 12 tests; hermetic via
  `tmp_path` + monkeypatched `environ`; no network, no mocks of the FS).
- Acceptance tests in `tests/integration/test_source_resolution_acceptance.py`
  (3–5 tests), including proof that `load_config` of a config whose tool is
  absent still succeeds (no `ConfigError` mapping).
- A "Resolving `project` / `system` sources" subsection added to
  `docs/config/reference.md § Source spec syntax`.

## Out of scope (deferred)

- **`PyPISource` network/registry resolution + venv creation** — STY-0006 /
  Environments. `resolve_source` rejects `pypi` with a typed error rather than
  reaching for the network; it never contacts an index.
- **`UnsupportedSource` (`local:` / `git:` / `docker:`)** — remain
  recognized-but-unsupported; `resolve_source` rejects them with a typed error.
- **Tokenizing `HookDef.run` into command + args, and running the executable** —
  the runner's job (PRD-0001 § Scope — Runner). `resolve_source` takes `tool`
  as an explicit bare-name string and does not tokenize `run`.
- **Workspace discovery** (walking up for `check.toml` / `pyproject.toml`) — the
  Workspace feature. STY-0005 takes `workspace_root` as an input (default
  `Path.cwd()`).
- **Windows `Scripts\` layout** and `.exe` / `PATHEXT` handling — POSIX `bin/`
  only in v1 per PRD-0001 § Open questions (Windows is a fast-follower). Locked
  as a documented later decision, not built here (see architecture-decision §6).
- **Cache key / hit-miss explainability** — PRD-0001 § Scope — Cache. `origin`
  is carried for runner explainability, but no cache key is produced.
- **The `.gitignore` `env/` un-ignore + committing `src/hooksmith/env/`** — a
  **separate chore** (STY-0005 TSK-008), deliberately kept OUT of this build.
  Because the resolver lands in `hooksmith.sources`, STY-0005 has no dependency
  on `hooksmith.env` and does not need that package committed. See § Split-out
  chore below.
- **New runtime dependencies** — none added; stdlib `os` / `shutil` / `pathlib`
  / `typing` plus the already-present `pydantic` are sufficient.

## Success criteria

Verbatim from
[STY-0005](../features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md)
Acceptance criteria:

- [ ] AC-1: `resolve_source(SystemSource(), tool)` for a tool present on `PATH`
  returns a `ResolvedTool` whose `executable` equals
  `Path(shutil.which(tool)).resolve()`, is absolute, exists, and whose
  `origin == "system"`.
- [ ] AC-2: `resolve_source(SystemSource(), tool)` for a tool **absent** from
  `PATH` raises `SourceResolutionError` whose `reason` is `not found on PATH`.
- [ ] AC-3: `resolve_source(ProjectSource(), tool)` with `VIRTUAL_ENV` pointing
  at a dir containing an executable `bin/<tool>` resolves to
  `<VIRTUAL_ENV>/bin/<tool>` (absolute) with `origin == "project"`.
- [ ] AC-4: `resolve_source(ProjectSource(), tool, workspace_root=root)` with no
  `VIRTUAL_ENV` and an executable `<root>/.venv/bin/<tool>` resolves there
  (absolute, `origin == "project"`).
- [ ] AC-5: When both an active `VIRTUAL_ENV` and `<root>/.venv` contain the
  tool, the `VIRTUAL_ENV` candidate wins (documented precedence).
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
  `(source, tool, PATH, VIRTUAL_ENV, workspace_root, fs)`, two calls return
  equal `ResolvedTool` values (or raise the same error).
- [ ] AC-11: `ResolvedTool.executable` is always an absolute `Path`.
- [ ] AC-12: `SourceResolutionError` subclasses `ValueError`; its message has
  the form `cannot resolve '<tool>' from <kind> source: <reason>`.
- [ ] AC-13: A resolution failure does **not** surface as `ConfigError` and is
  **not** raised from `load_config` — loading a config whose tool is absent
  succeeds; the error only appears when `resolve_source` is called.
- [ ] AC-14: `from hooksmith.sources import resolve_source, ResolvedTool,
  SourceResolutionError` works.
- [ ] AC-15: `mypy --strict src/hooksmith/sources/` passes with no new errors;
  the `match` over `ParsedSource` narrows the `SystemSource` / `ProjectSource`
  cases cleanly.
- [ ] AC-16: No new runtime dependencies added (`os`, `shutil`, `pathlib`,
  `typing` only, plus existing `pydantic`).

## Stakeholder dependencies

- **[STY-0004](../features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md)**
  — merged; provides the `hooksmith.sources` package, the four `kind`-models,
  the `ParsedSource` plain-union alias, and `parse_source`. STY-0005 **consumes
  and extends** this package; the union alias is the `match` surface. No blocker;
  this is the integration surface and must not be reshaped.
- **[STY-0006](../features/FEAT-0002-source-resolution/stories/) (not yet
  written)** — the downstream boundary. `resolve_source` rejects `PyPISource`
  with a typed error whose reason names STY-0006 as the owner of `pypi`
  resolution. STY-0005 does not implement any network path.
- **`hooksmith.config`** — `HookDef.run` is where the runner will derive `tool`
  (first shell token); `HookDef.from_` feeds `parse_source`. STY-0005 does
  **not** import `hooksmith.config`; it receives `tool` as an explicit argument,
  keeping `sources` a leaf. No blocker.
- **pydantic (>=2)** — already a runtime dep since STY-0001. No new install.
- **Locked architecture:**
  [0005-architecture-decision.md](0005-architecture-decision.md) — the
  code / test / review lanes consume it; any change re-opens BUILD-0005 §1.

## Split-out chore (deliberately NOT in this build)

STY-0005 TSK-008 is raised as its **own chore**, separate from this build: the
bare `env/` line in `.gitignore` (intended for virtualenvs) also matches
`src/hooksmith/env/`, so that package (`manager.py`, `__init__.py`) is silently
uncommitted. Because STY-0005's resolver lands in `hooksmith.sources`, this
build has **no** dependency on the env package and does **not** need it
committed. Bundling the un-ignore + making the entire Environments scaffold
`ruff` / `mypy --strict` clean is unrelated scope that would bloat a focused
resolution PR and couple it to a feature (Environments) not yet being built.
The chore must: fix `.gitignore` (anchor `/env/` or add
`!src/hooksmith/env/`), commit the package, and make it `ruff` / `mypy
--strict` clean — including landing BUILD-0004's already-applied-but-uncommitted
`config.schema` → `config.hook_def` import fix in `env/manager.py`, which is
invisible to git while the package is ignored.

## Cross-references / boundary notes

- **STY-0006 boundary:** `resolve_source` is the typed hand-off point. The
  Environments feature's `EnvManager.resolve(hook)` will **delegate** the
  `project` / `system` kinds to `resolve_source` and own only the `pypi:`
  venv-creation path. `ResolvedTool` (a single located binary) is intentionally
  *not* the `ResolvedEnv` (bin dir + cache key) shape — the abstractions differ.
- **Why no `ConfigError` mapping:** a resolution failure is a
  runtime/environment condition (the `from` / `run` are syntactically valid; the
  tool is absent on this machine now), with no `check.toml:line:col` meaning.
  Unlike `SourceSpecError` (a load-time *syntax* error wrapped by the config
  layer), `SourceResolutionError` is never raised from `load_config` and never
  wrapped as `ConfigError` (AC-13). See architecture-decision §5.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | `match` over `ParsedSource` fails to narrow `SystemSource` / `ProjectSource` under `mypy --strict`. | Low | Med — AC-15 gate fails; `# type: ignore` creeps in. | `ParsedSource` is already a plain union (STY-0004); `case SystemSource()` / `case ProjectSource()` narrow cleanly. AC-15 gate + no-`type: ignore` rule catch regressions. |
| R2 | A resolution failure is accidentally wrapped as `ConfigError` (e.g. someone eagerly resolves in `load_config`). | Low | High — breaks AC-13; loading a config becomes machine-dependent. | `resolve_source` lives in `sources`, is hook- and location-free, and is never called from `load_config`. Acceptance test loads a config with an absent tool and asserts success. |
| R3 | Non-absolute or symlink `executable` leaks to the runner. | Low | Med — runner gets a relative/ambiguous path. | Always `Path(...).resolve()` the located candidate (both branches); AC-11 asserts absolute. Regular-file check follows symlinks so a broken symlink is not returned. |
| R4 | `.venv`/`VIRTUAL_ENV` precedence diverges from the documented order, or a non-executable candidate is returned. | Low | Med — surprising resolution; AC-5 / AC-7 fail. | Locked precedence (VIRTUAL_ENV then `.venv`), first qualifying wins; each candidate must exist + be a regular file + `os.access(p, os.X_OK)`. Tests assert precedence and non-executable skip. |
| R5 | Scope creep into venv creation on a missing `.venv`. | Low | High — violates the story's core boundary (AC-9). | A missing `.venv` is a not-found error, never a create trigger. No writes/subprocess anywhere; hermetic `tmp_path` tests confirm nothing is created. |
