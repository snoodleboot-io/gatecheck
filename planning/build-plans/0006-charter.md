---
id: BUILD-0006-CHARTER
title: Build charter for STY-0006 (resolve pypi / pypi+alias sources against a registry)
parent: BUILD-0006
target_story: STY-0006
status: Locked
date: 2026-07-05
---

# BUILD-0006 Charter — STY-0006 (Resolve `pypi:` / `pypi+alias:` specs to a pinned distribution)

## Goal

Give the **network** `ParsedSource` kind — `PyPISource` — a *pinned version*.
Deliver a synchronous
`resolve_pypi_source(source, sources, *, client=None, allow_prereleases=False) ->
ResolvedPyPISource` in a **new leaf package** `src/hooksmith/registry/` that turns
a `PyPISource` (its verbatim `requirement` + optional registry `alias`) into a
concrete, frozen `ResolvedPyPISource` (`name` + exact `version` + `index_url`,
plus best-effort `sha256`/`url`/`filename`) by querying a **PEP 503 simple index**
(PEP 691 JSON with PEP 503 HTML fallback) over stdlib `urllib`. This is the
**Sources → Environments boundary**: it produces the pinned descriptor;
Environments (uv-backed) consumes it to build a cached venv.

This is the third vertical slice of FEAT-0002 — the network half that STY-0005's
`resolve_source` deliberately deferred ("pypi source resolution is delegated to
Environments (STY-0006)"). **Query + version-math only: NO venv creation, NO
artifact download, NO install.** See
[STY-0006](../features/FEAT-0002-source-resolution/stories/STY-0006-resolve-pypi-registry-specs.md),
[FEAT-0002](../features/FEAT-0002-source-resolution/feature.md),
[PRD-0001 § Scope — Sources](../prd/0001-hooksmith.md#scope), and
[ADR-0001](../adr/0001-python-host-rust-core.md).

## Design-gate approvals (GRANTED — build to these)

1. **New runtime dependency `packaging>=24`** (PEP 440 `SpecifierSet`/`Version`,
   PEP 508 `Requirement`, `parse_wheel_filename`/`parse_sdist_filename`,
   `canonicalize_name`). Exactly **one** new dependency; HTTP + parsing stay on
   stdlib (`urllib`, `json`, `html.parser`) — **no** `httpx`/`requests`.
2. **Config-schema change:** add `extra_registries: dict[str, str]` (alias
   `extra-registries`, default empty) to `hooksmith.config.SourceSpec`.
3. **Registry approach:** PEP 503 simple index + PEP 691 JSON content negotiation,
   **not** the Warehouse JSON API (JSON API is PyPI-only and would break
   `pypi+alias:` private registries).

## In-scope for this build

Single-PR vertical slice. New code lands in a new leaf package
`src/hooksmith/registry/` (one class/function-group per file, per core
conventions); the config-schema change (TSK-001) is carved so it can land as its
own reviewable commit within the PR:

- `src/hooksmith/registry/resolved_pypi_source.py` — `ResolvedPyPISource` frozen
  pydantic model (`kind`, `requirement`, `name`, `version`, `index_url`,
  `registry`; optional `sha256`/`url`/`filename`; `ConfigDict(frozen=True,
  extra="forbid")`).
- `src/hooksmith/registry/registry_error.py` — `RegistryError(ValueError)` with
  structured `requirement` / `index_url` / `reason` and the `cannot resolve
  '<req>' against <index>: <reason>` message.
- `src/hooksmith/registry/registry_client.py` — the `RegistryClient` Protocol
  (`fetch_project(index_url, name) -> ProjectPage`), `ProjectPage` / `ProjectFile`
  value objects, the `PackageNotFound` / `MalformedIndexResponse` fetch-failure
  signals, and `UrllibRegistryClient` (stdlib `urllib`, PEP 691 `Accept` + PEP 503
  HTML fallback).
- `src/hooksmith/registry/index_resolver.py` — `resolve_index_url(alias, sources)`
  (default vs `extra_registries`; built-in `https://pypi.org/simple` fallback;
  unknown alias → `RegistryError` with `index_url=None`). Pure, no network.
- `src/hooksmith/registry/pypi_resolver.py` — `resolve_pypi_source(...) ->
  ResolvedPyPISource` plus private version-selection helpers (the 8-step
  algorithm; no class).
- `src/hooksmith/registry/__init__.py` — facade exporting `ProjectFile`,
  `ProjectPage`, `RegistryClient`, `RegistryError`, `ResolvedPyPISource`,
  `UrllibRegistryClient`, `resolve_pypi_source` (alphabetical, uppercase-first).
- `src/hooksmith/config/source_spec.py` — **EDIT** adding `extra_registries:
  dict[str, str]` (alias `extra-registries`, default empty) + a `field_validator`
  (alias `[A-Za-z0-9_-]+`, non-empty URL). (TSK-001)
- `pyproject.toml` — add `packaging>=24` to `[project].dependencies`; register the
  `network` pytest marker. (TSK-002)
- Unit tests `tests/unit/test_pypi_resolver.py` (≥15 tests; hermetic via
  `FakeRegistryClient`; no network) and `tests/unit/test_registry_client.py`
  (client-level, loopback `http.server` / `urlopen` monkeypatch).
- Acceptance tests `tests/integration/test_pypi_resolution_acceptance.py` (3–5
  hermetic tests), including proof that `load_config` of a `pypi:` hook succeeds
  with no `ConfigError` (network resolution is not run at load time).
- A "Resolving `pypi:` / `pypi+alias:` sources" subsection added to
  `docs/config/reference.md § Source spec syntax`, plus the `extra-registries`
  documentation correction (see § Deviations).

## Out of scope (deferred)

- **Venv creation / artifact download / installation** — Environments (uv-backed).
  This story returns a descriptor only.
- **Dependency-graph / transitive resolution + hash-pinning the closure** — uv's
  job at env-build time; this story pins the single hook requirement.
- **Platform/interpreter-specific wheel selection** — uv's job; the best-effort
  artifact fields pick one representative file (wheel-preferred), not the
  target-platform wheel.
- **Caching the registry response / resolved version** — Cache feature; each call
  queries live.
- **Auth to private indexes** (tokens / `.netrc` / keyring) — documented
  fast-follower; the `RegistryClient` seam is the extension point.
- **PEP 508 markers / extras** — **rejected** with a clear `RegistryError`, not
  silently ignored.
- **The undeclared-alias `ConfigError` validator (TSK-008)** — deferred. An
  undeclared alias surfaces as `RegistryError` at resolve time (AC-6), not as a
  load-time `ConfigError`. See architecture-decision §8.
- **`project` / `system` / `UnsupportedSource` kinds** — STY-0005's
  `resolve_source`, unchanged. `resolve_source` is **not** modified (AC-21).
- **The Warehouse JSON API** — rejected in favour of PEP 503 + PEP 691.

## Success criteria

Verbatim from
[STY-0006](../features/FEAT-0002-source-resolution/stories/STY-0006-resolve-pypi-registry-specs.md)
Acceptance criteria (AC-1 … AC-21). Highlights:

- [ ] AC-1: `resolve_pypi_source(PyPISource(requirement="ruff==0.4.9"), sources)`
  against a fake index carrying `0.4.9` returns `ResolvedPyPISource(name="ruff",
  version="0.4.9", index_url=<default>, registry=None, kind="pypi")`.
- [ ] AC-2: For `ruff>=0.4,<1` with `0.4.1`/`0.4.9`/`1.0.0`, the highest satisfying
  version (`0.4.9`) is selected.
- [ ] AC-3: A bare name selects the latest non-pre-release version.
- [ ] AC-4: `registry=None` → `sources.default_registry` (or built-in
  `https://pypi.org/simple` when `sources` is `None`/unset).
- [ ] AC-5: `registry="internal"` → `sources.extra_registries["internal"]`.
- [ ] AC-6: Undeclared alias → `RegistryError` naming the alias and
  `[sources].extra-registries`, with `index_url is None`.
- [ ] AC-7: Package 404 → `RegistryError` (package not found), never a crash.
- [ ] AC-8: No version satisfies → `RegistryError` (no version satisfies).
- [ ] AC-9: Pre-release excluded by default; included when the specifier opts in or
  `allow_prereleases=True`; selected when only pre-releases satisfy.
- [ ] AC-10: Yanked excluded from a range but selectable when pinned exactly
  (`==<yanked>`) and the only match (PEP 592).
- [ ] AC-11: Network failure / malformed body → `RegistryError` (network wrapped
  via `raise … from`), never a raw `urllib`/parse exception.
- [ ] AC-12: `sha256`/`url`/`filename` reflect the selected version's chosen file
  (wheel preferred); `None` when unavailable — resolution still succeeds on
  `name`+`version`+`index_url`.
- [ ] AC-13: No venv creation, no artifact download, no install (verifiable via a
  `FakeRegistryClient` recording only `fetch_project`).
- [ ] AC-14: Every unit test hermetic; default suite makes no real network call;
  any real-PyPI test is `@pytest.mark.network` and skipped by default.
- [ ] AC-15: `resolve_pypi_source` is deterministic for a fixed `(source, sources,
  fake response)`.
- [ ] AC-16: `RegistryError` subclasses `ValueError`; message `cannot resolve
  '<requirement>' against <index>: <reason>`.
- [ ] AC-17: A registry/resolution failure does not surface as `ConfigError` and is
  not raised from `load_config`; loading a `pypi:` hook succeeds. (TSK-008
  deferred, so this holds unconditionally.)
- [ ] AC-18: `from hooksmith.registry import resolve_pypi_source,
  ResolvedPyPISource, RegistryClient, RegistryError` works.
- [ ] AC-19: `mypy --strict src/hooksmith/registry/` passes with no new errors.
- [ ] AC-20: Dependency delta is exactly `packaging>=24`; no HTTP client added.
- [ ] AC-21: `resolve_source` (STY-0005) unchanged; `hooksmith.sources` gains no
  network I/O.

## Stakeholder dependencies

- **[STY-0004](../features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md)**
  — merged; provides `PyPISource(requirement, registry)` (the resolver's input)
  and the alias charset `[A-Za-z0-9_-]+` the config validator mirrors. Integration
  surface; not reshaped.
- **[STY-0005](../features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md)**
  — merged; its `resolve_source` `PyPISource` rejection names STY-0006 as the
  owner of `pypi` resolution. This build **fulfils** that promise from a **separate
  entry point** and does **not** modify `resolve_source` (AC-21).
- **`hooksmith.config`** — `HooksmithConfig.sources` (`SourceSpec`) is extended
  with `extra_registries` (TSK-001); the pydantic → `ConfigError` translation
  already in `load_config` carries the validator's errors with `line:col`. No new
  config plumbing.
- **`packaging>=24`** — NEW runtime dependency (design-gate approved). Ships
  `py.typed`; **no** mypy override needed (contrast `hooksmith_core`).
- **pydantic (>=2)** — already a runtime dep. No new install beyond `packaging`.
- **Environments (`hooksmith.env`, not yet built)** — the downstream consumer of
  `ResolvedPyPISource`; out of scope here.
- **Locked architecture:**
  [0006-architecture-decision.md](0006-architecture-decision.md) — the
  code / test / review lanes consume it; any change re-opens BUILD-0006 §1.

## Deviations from the story (flag at review)

1. **`extra-registries` docs shape is inconsistent with the `dict[str,str]`
   model.** `docs/config/reference.md § [sources]` currently documents
   `extra-registries` as a **"list of `{alias = url}`"** with an example array of
   inline tables:
   ```toml
   extra-registries = [ { internal = "https://pkg.example.com/simple" } ]
   ```
   The approved model is `dict[str, str]`, which deserializes from a TOML **table**
   (`[sources.extra-registries]` / inline `{ internal = "..." }`), **not** an array
   of tables. A list of inline tables would not load into `dict[str, str]` without
   a bespoke merge-validator, and would not round-trip cleanly through
   `dump_config`. **Locked resolution:** keep the model as `dict[str, str]` (per
   AC-5 + design gate) and **correct the docs** (TSK-013) to the table form. This
   is a documentation fix, not a scope change; flagged so the reviewer approves the
   doc correction alongside the schema.

2. **Function/module names follow the STORY, not the design-gate brief's
   shorthand.** The brief referenced `resolve_pypi(...)` in `resolver.py`; the
   story (AC-1, TSK-009) and `resolve_source`'s reference message use
   **`resolve_pypi_source`** in **`pypi_resolver.py`**, with alias resolution split
   into **`index_resolver.py`**. Locked to the story's names for consistency with
   the existing rejection message and ACs.

No other deviations: package placement (`hooksmith.registry`), the single
`packaging>=24` dependency, PEP 503+691 approach, the injected-client seam,
best-effort artifact fields, and the `RegistryError` shape all match the story
verbatim.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|------|------------|--------|------------|
| R1 | PEP 440 pre-release / yanked selection diverges from pip/`packaging` semantics (AC-9/AC-10). | Med | High — wrong version pinned; surprising installs. | Use `SpecifierSet.filter(prereleases=…)` (never hand-rolled), `_prereleases_flag = True if allow_prereleases else None`; PEP 592 yanked handled explicitly (exclude unless exact-pin sole match). Dedicated tests for each rule. |
| R2 | `dict[str,str]` model vs documented list-of-tables TOML causes existing/user configs to fail to load, or breaks `dump_config` round-trip. | Med | Med — config regressions. | Field is optional, empty default → omitted by `exclude_defaults` (existing round-trip unchanged). Docs corrected (Deviation 1). Round-trip test for a non-empty `extra-registries`. |
| R3 | A real `urllib` call leaks into the default (hermetic) suite (AC-14). | Low | Med — flaky/networked CI. | Network boundary is the injected `RegistryClient`; resolver suite uses `FakeRegistryClient` only; the one real-PyPI test is `@pytest.mark.network`, skipped by default; `UrllibRegistryClient` tested against loopback `http.server`. |
| R4 | Client raises a raw `urllib`/parse exception that escapes as-is (AC-11). | Low | Med — opaque errors to callers. | Client raises only `PackageNotFound`/`MalformedIndexResponse` or lets `URLError`/`TimeoutError`/`OSError` propagate; resolver catches all and wraps in `RegistryError` (network via `raise … from`). Tests assert wrapping. |
| R5 | Accidentally running network resolution at `load_config` time (breaks AC-17). | Low | High — loading a config becomes network-dependent. | `resolve_pypi_source` lives in `registry`, never called from `load_config`; TSK-008 deferred; acceptance test loads a `pypi:` hook and asserts success with no `ConfigError`. |
| R6 | `mypy --strict` friction on `packaging` return tuples / Protocol. | Low | Low — AC-19 gate; `# type: ignore` creep. | `packaging` ships `py.typed`; destructure `parse_*_filename` tuples with explicit types; `RegistryClient` is a plain `Protocol`. No override, no ignores. |
