---
id: STY-0006
title: Resolve `pypi:` / `pypi+alias:` specs against a registry to a pinned distribution
status: Draft
owner: TBD
date: 2026-07-05
feature: FEAT-0002
prd: PRD-0001 § Scope — Sources (Environments boundary)
adrs: [ADR-0001]
---

# STY-0006: Resolve `pypi:` / `pypi+alias:` specs against a registry to a pinned distribution

## As a / I want / So that

As a **hooksmith developer**, I want **a `resolve_pypi_source(source, sources)`
function that turns a `PyPISource` — its `requirement` and optional registry
`alias` — into a concrete, pinned distribution descriptor by querying the
registry index over the network** so that **the Environments feature can build a
deterministic, uv-backed venv from an exact `name==version` against a known index
URL, instead of re-deriving the index, re-parsing the requirement, or re-picking
a version at env-build time**.

## Scope

STY-0004 gave a hook's `from` string *meaning* (`parse_source` →
`PyPISource(requirement, registry)`), and STY-0005 gave the two **non-network**
kinds *location* (`resolve_source` → `ResolvedTool`). STY-0004/0005 deliberately
stopped at the network boundary: `resolve_source` **rejects** a `PyPISource`
with `SourceResolutionError("pypi source resolution is delegated to Environments
(STY-0006), not handled here")`. This story lights up that path — it gives a
`PyPISource` a **pinned version** by talking to the registry:

- Resolve the registry **alias → index URL** (`registry=None` → default index;
  `registry="internal"` → a URL declared in `[sources]`).
- **Query the index over the network** for the requirement's project, collect the
  available versions, and select the **best version** satisfying the PEP 440
  specifier — honouring pre-release and yanked-release rules.
- Produce a typed, frozen `ResolvedPyPISource` (name + exact version + index URL,
  plus optional artifact metadata) that the Environments feature consumes.

This is **the Sources → Environments boundary.** STY-0006 produces the *pinned
dist descriptor*; it does **not** create or populate a venv, download the
artifact, or install anything — that is the Environments feature (PRD-0001
§ Scope — Environments).

Explicitly **out of scope**:
- **Venv creation / artifact download / installation.** Environments (uv-backed)
  owns building the env from the descriptor this story returns.
- **Dependency-graph / transitive resolution.** STY-0006 resolves the *single*
  hook requirement to one pinned version. Full dependency resolution (and hash
  pinning of the transitive closure) is uv's job at env-build time.
- **Platform/interpreter-specific wheel selection.** Choosing the exact wheel for
  the target interpreter/ABI/platform is uv's job (it depends on the env being
  built, which Environments owns). See § Output model for how far this story goes.
- **`project` / `system` / `UnsupportedSource` kinds** — resolved (or rejected)
  by STY-0005's `resolve_source`; unchanged here.
- **Caching the registry response or the resolved version** (PRD-0001 § Scope —
  Cache). Each call queries live; a resolution cache layers on later.
- **Authentication to private indexes** (tokens, `.netrc`, keyring). v1 targets
  anonymous / already-credentialed indexes; auth is a documented fast-follower
  (see Notes). The injected client seam is where auth later plugs in.

### Prerequisite gap — `[sources]` schema has no alias → URL map (IN SCOPE)

**Critical dependency, flagged per core conventions.** The `docs/config/reference.md
§ [sources]` table already *documents* two fields:

| Key | Type | Default | Meaning |
|---|---|---|---|
| `default-registry` | string | PyPI | Index URL for `pypi:` sources |
| `extra-registries` | list of `{alias = url}` | `[]` | Named private indexes |

…but the implemented model `hooksmith.config.SourceSpec` **only has
`default_registry`**. There is **no `extra_registries` field**, so today there is
**no way to map `pypi+internal:` → an index URL**. Without it, this story cannot
resolve any `pypi+alias:` spec.

**Decision: the `extra_registries` schema extension is IN THIS STORY** (TSK-001),
not a separate prerequisite. Rationale: it is a single documented-but-unimplemented
`Field` addition on an existing model (small, low-risk), the docs already commit to
its exact shape, and it is a hard dependency for the story's core value. It is
carved into its own task so it can be reviewed/landed independently if the
design gate prefers to split it.

Note this modifies `src/hooksmith/config/source_spec.py`, a config-schema file —
call out at the design gate so the human approves the schema change alongside the
new dependency.

### NEW DEPENDENCIES — design gate (HARD STOP: approve before implementing)

Per core conventions ("Prefer standard library over third-party where equivalent";
"Flag any new dependency before adding it"), the proposed dependency delta is:

| Need | Recommendation | New dep? | Rationale |
|---|---|---|---|
| HTTP client | stdlib **`urllib.request`** | **No** | PRD "prefer stdlib". A single `GET` of a simple-index page needs no third-party client. `httpx`/`requests` give a nicer API but add a dependency (and `httpx` pulls a tree) for no capability we need. **Recommend against** `httpx`/`requests`. |
| Simple-index parse | stdlib **`json`** (PEP 691) with stdlib **`html.parser`** fallback (PEP 503 HTML) | **No** | Request `Accept: application/vnd.pypi.simple.v1+json`; parse JSON. If a registry only serves HTML, fall back to `html.parser`. Both stdlib. |
| PEP 440 version + specifier handling; wheel/sdist filename parsing; name canonicalization | **`packaging`** (`SpecifierSet`, `Version`, `Requirement`, `parse_wheel_filename`, `parse_sdist_filename`, `canonicalize_name`) | **Yes — 1 new runtime dep** | Correct PEP 440 pre-release/ordering semantics and PEP 508 requirement parsing are effectively impossible to get right by hand; `packaging` is the de-facto standard (pip/uv/setuptools depend on it). A stdlib reimplementation is **not recommended** — it would silently mis-order pre-releases and mishandle local/epoch versions. |

**Proposed dependency delta: exactly ONE new runtime dependency — `packaging>=24`.**
HTTP and index parsing stay on the standard library. The human approves/denies
this single addition at the design gate before TSK work begins.

### Registry approach — PEP 503 simple index (RECOMMENDED), not the PyPI JSON API

Two ways to enumerate a project's versions:

- **PyPI JSON API** — `GET {host}/pypi/{name}/json`. Rich (versions, files, hashes,
  yanked flags in one JSON doc) but **PyPI/Warehouse-specific**. Private indexes
  (devpi, Artifactory, Nexus, GitLab, AWS CodeArtifact) generally do **not** serve
  it. Using it would make `pypi+alias:` — the private-registry story that is half
  the point of hooksmith — unresolvable.
- **PEP 503 "simple" index** — `GET {index_url}/{canonical_name}/`. A **universal
  standard** every index implements; PEP 691 adds a JSON representation via content
  negotiation. The configured `default-registry` (`https://pypi.org/simple`) is
  *already a simple-index URL*, and `extra-registries` are simple-index URLs too.

**RECOMMENDATION: the PEP 503 simple index, with PEP 691 JSON content negotiation
(`Accept: application/vnd.pypi.simple.v1+json`) and an HTML fallback.** It is the
only approach that works uniformly across PyPI and private registries, and it
matches the URL shape the config already stores.

### Where the new code lives — **recommendation: a new `src/hooksmith/registry/` package**

STY-0004/0005 built `hooksmith.sources` as a **pure, dependency-light, no-I/O
leaf** (its ACs assert "no network, no subprocess"). STY-0006 is the opposite: it
performs network I/O and pulls in `packaging` + `urllib`. Landing it *inside*
`hooksmith.sources` would contradict that package's established character.

**Recommendation: a new leaf package `src/hooksmith/registry/`** — the network
"resolve a requirement against an index" concern — giving a clean three-way split:

- `hooksmith.sources` — classify a `from` spec (`parse_source`) and locate the
  local kinds (`resolve_source`). Pure, no I/O. **Unchanged by this story.**
- `hooksmith.registry` — query an index and pin a `pypi:` requirement to a
  concrete distribution. Network + `packaging`. **New, this story.**
- `hooksmith.env` — build/cache the uv-backed venv from the pinned descriptor.
  The Environments feature. Consumes this story's output.

`resolve_source`'s `PyPISource` branch stays **unchanged** — it still rejects
`pypi` with `SourceResolutionError` ("delegated to Environments"). The `pypi`
network path is a **separate entry point** (`registry.resolve_pypi_source`) that
the Environments `EnvManager` calls directly. This preserves STY-0005's contract
verbatim and keeps `sources` pure.

**Architect to lock:** `hooksmith.registry` (recommended) vs
`hooksmith.sources.pypi_resolver` (more cohesive with FEAT-0002 but contaminates
the pure leaf). The story is written around `hooksmith.registry`.

Files (one class/function-group per file per core conventions):

| File | Single responsibility |
|---|---|
| `src/hooksmith/registry/resolved_pypi_source.py` | `ResolvedPyPISource` frozen pydantic model (the pinned descriptor). |
| `src/hooksmith/registry/registry_error.py` | `RegistryError(ValueError)` with structured fields. |
| `src/hooksmith/registry/registry_client.py` | `RegistryClient` Protocol (the network seam) + `UrllibRegistryClient` default impl (stdlib `urllib`). |
| `src/hooksmith/registry/index_resolver.py` | Alias → index-URL resolution against a `SourceSpec`. |
| `src/hooksmith/registry/pypi_resolver.py` | `resolve_pypi_source(...) -> ResolvedPyPISource` + private version-selection helpers. No class. |
| `src/hooksmith/registry/__init__.py` | Facade — export the public symbols; set `__all__`. |

### Input / output contract (describe — do not implement)

```python
# pypi_resolver.py
def resolve_pypi_source(
    source: PyPISource,
    sources: SourceSpec | None,
    *,
    client: RegistryClient | None = None,
    allow_prereleases: bool = False,
) -> ResolvedPyPISource: ...
```

- **`source`** — the `PyPISource` from `parse_source(hook.from_)`, carrying the
  verbatim `requirement` and the optional registry `alias` (`registry`).
- **`sources`** — the parsed `[sources]` table (`HooksmithConfig.sources`, may be
  `None`). Supplies `default_registry` and the new `extra_registries` alias map.
- **`client`** — the injectable network seam (see § Hermetic testing). Defaults to
  `UrllibRegistryClient()`. Tests pass a fake; auth/proxy config plugs in here later.
- **`allow_prereleases`** — caller override for pre-release selection (default
  `False`; see rules). The specifier itself can still opt in per PEP 440.

**Returns** a `ResolvedPyPISource` — a frozen pydantic `BaseModel`
(`model_config = ConfigDict(frozen=True, extra="forbid")`, mirroring the STY-0004
source models):

| Field | Type | Meaning |
|---|---|---|
| `kind` | `Literal["pypi"]` = `"pypi"` | Discriminator, consistent with `PyPISource`. |
| `requirement` | `str` | The original requirement text, echoed back. |
| `name` | `str` | The **canonicalized** project name (`packaging.utils.canonicalize_name`). |
| `version` | `str` | The **selected** exact version (`str(Version)`), e.g. `"0.4.9"`. |
| `index_url` | `str` | The resolved index URL the version was pinned against. |
| `registry` | `str \| None` | The `[sources]` alias used, or `None` for the default. |
| `sha256` | `str \| None` | *(optional, best-effort)* hash of the chosen file, from the PEP 503 URL fragment. |
| `url` | `str \| None` | *(optional, best-effort)* download URL of the chosen file. |
| `filename` | `str \| None` | *(optional, best-effort)* filename of the chosen file. |

**Load-bearing contract = `name` + `version` + `index_url`** — enough for
Environments to install `name==version --index-url <index_url>` deterministically.
The optional `sha256` / `url` / `filename` are best-effort metadata (from the
selected version's simple-index entry) for supply-chain hash-pinning and cache/
explainability; they are **not** authoritative artifact selection — the exact
wheel for the target platform is uv's job at env-build time.

**Architect to lock:** whether to populate the optional artifact fields now (they
come "for free" from the simple index and enable hash-pinned installs) or defer
them entirely to Environments/uv to keep the boundary minimal. Story recommends
populating them best-effort, `None` when unavailable.

### Error type / behavior

A dedicated **`RegistryError(ValueError)`** in
`src/hooksmith/registry/registry_error.py`, mirroring `SourceResolutionError`'s
shape (subclasses `ValueError`; structured fields; location-free):

```python
class RegistryError(ValueError):
    requirement: str
    index_url: str | None    # None when the failure is alias resolution (no URL yet)
    reason: str
    def __init__(self, requirement: str, index_url: str | None, reason: str) -> None:
        self.requirement = requirement
        self.index_url = index_url
        self.reason = reason
        loc = index_url or "<unresolved index>"
        super().__init__(f"cannot resolve '{requirement}' against {loc}: {reason}")
```

Why a **new** type (not reuse `SourceResolutionError`): SRP — network/registry
failures are a different failure domain than PATH/venv lookups, with different
diagnostic fields (`requirement`/`index_url` vs `tool`/`kind`). It subclasses
`ValueError` to stay consistent with `SourceSpecError` / `SourceResolutionError` /
`ConfigError`.

Failure cases and their reasons:

| Case | Error | `reason` (illustrative) |
|---|---|---|
| Unknown registry alias (`pypi+internal:` with no `internal` in `extra-registries`) | `RegistryError` (`index_url=None`) — **see below re: ConfigError** | `unknown registry alias 'internal' (not declared in [sources].extra-registries)` |
| Package not found (index 404 for the project) | `RegistryError` | `package 'ruff' not found on index` |
| No version satisfies the specifier | `RegistryError` | `no version of 'ruff' satisfies '>=99'` |
| Network / timeout (`URLError`, socket timeout) | `RegistryError` (wraps the cause via `raise … from`) | `network error querying index: <detail>` |
| Malformed index response (unparseable JSON/HTML) | `RegistryError` | `malformed index response from <url>` |

**Which map to `ConfigError`?** Only the **unknown-alias** case has any
config-time meaning; the network cases (404 / no-match / timeout / malformed) are
**runtime/environment** conditions and never map to `ConfigError` (they have no
`check.toml:line:col`).

- **Decision on unknown alias:** an undeclared alias is a config *authoring*
  mistake — statically knowable from `check.toml` (the hook's `from` alias vs the
  `[sources].extra-registries` keys), so it *does* have a `line:col` meaning. But
  to mirror STY-0005's clean separation, the **resolver itself stays location-free
  and raises `RegistryError`**. Surfacing it as a `ConfigError` at load time is a
  **cross-field config validation** — recommended as **its own follow-up task**
  (TSK-008, optional/deferrable), *not* baked into the network resolver. If that
  validator lands, an undeclared alias is caught at `load_config` with
  `check.toml:line:col`; if it does not, the same mistake surfaces as
  `RegistryError` at resolve time. Either way the network path never fabricates a
  `line:col`.

### Resolution algorithm (precise, deterministic given a fixed index response)

1. **Resolve the index URL** (`index_resolver.py`): if `source.registry is None`
   → `sources.default_registry` if set, else the built-in default
   `https://pypi.org/simple`. If `source.registry == "<alias>"` →
   `sources.extra_registries["<alias>"]`; missing key → `RegistryError`
   (unknown alias, `index_url=None`).
2. **Parse the requirement** (`packaging.requirements.Requirement`): derive the
   project name and `SpecifierSet`. This is where PEP 508 parsing finally happens
   (deferred verbatim from STY-0004). A bare name (`ruff`) → empty specifier
   (select latest). Malformed requirement → `RegistryError` (invalid requirement).
   Markers/extras are out of scope — document as ignored/rejected (architect locks
   which; recommend reject-with-clear-error to avoid silent surprises).
3. **Fetch the project page** via `client.fetch_project(index_url, canonical_name)`
   — `GET {index_url}/{canonical_name}/` with the PEP 691 `Accept` header. 404 →
   `RegistryError` (package not found). Network error → `RegistryError` (wrap).
   Unparseable body → `RegistryError` (malformed).
4. **Enumerate versions** from the returned files: derive each file's version with
   `packaging.utils.parse_wheel_filename` / `parse_sdist_filename`; record the
   per-file `yanked` flag (PEP 592) and hash (URL fragment).
5. **Filter by specifier + pre-release rules:** use `SpecifierSet.filter(versions,
   prereleases=…)`. Pre-releases are excluded unless (a) the specifier explicitly
   permits them, (b) `allow_prereleases=True`, or (c) *only* pre-releases satisfy
   the specifier — matching pip/`packaging` semantics.
6. **Apply yanked rules (PEP 592):** exclude yanked versions **unless** the
   specifier pins that exact version (`==X`) and it is the only match — then it is
   selectable (with a note reserved for the future explainability trace).
7. **Select** the **highest** remaining `Version`. None remain → `RegistryError`
   (no version satisfies). Pick the file for that version (prefer a wheel; else the
   sdist) for the optional `url`/`sha256`/`filename` fields.
8. **Return** `ResolvedPyPISource(kind="pypi", requirement=source.requirement,
   name=canonical_name, version=str(selected), index_url=index_url,
   registry=source.registry, sha256=…, url=…, filename=…)`.

**Determinism:** given the same `(source, sources, index response)` the function
returns an equal `ResolvedPyPISource` (or raises the same `RegistryError`). The
only non-determinism is the live index; the injected `client` makes it a pure
function of its inputs in tests.

### Hermetic testing — inject the network seam (no real network in the suite)

Unit tests **must** be hermetic — **no real network**. The network boundary is a
**dependency-injected seam**, mirroring STY-0005's injectable `environ` /
`workspace_root`:

- `RegistryClient` is a **`typing.Protocol`** with a single method, e.g.
  `fetch_project(index_url: str, name: str) -> ProjectPage` (a small typed value
  object listing files: filename, url, hash, yanked). The default
  `UrllibRegistryClient` implements it over stdlib `urllib.request`.
- `resolve_pypi_source(..., client=None)` defaults to `UrllibRegistryClient()`;
  tests pass a `FakeRegistryClient` returning canned `ProjectPage` fixtures (from
  captured PEP 691 JSON / PEP 503 HTML snippets). **No monkeypatching of
  `urllib`** is needed because the seam is a parameter — cleaner and mypy-strict
  friendly. (A `monkeypatch` of `urllib.request.urlopen` is the fallback if the
  architect prefers not to expose the client parameter, but DI is recommended.)
- The default unit suite is fully offline and deterministic. A single **optional**
  real-PyPI smoke test may be marked `@pytest.mark.network` and **skipped by
  default** so the CI gate stays hermetic (architect locks whether to include it).

Test the `UrllibRegistryClient` itself against a **local `http.server`** (stdlib,
loopback) or by monkeypatching `urlopen` — not the public internet — so even the
real client's parse/HTTP-status handling is covered without leaving the machine.

### Sources → Environments boundary (explicit hand-off)

STY-0006 is the seam between FEAT-0002 (Sources) and the Environments feature:

```
parse_source(hook.from_)        # STY-0004  → PyPISource(requirement, registry)
        │
        ▼
resolve_pypi_source(src, cfg.sources)   # STY-0006 (this story) → ResolvedPyPISource
        │  (name==version, index_url [, sha256])
        ▼
EnvManager.resolve(hook)        # Environments → builds/caches a uv venv from the
                                #   pinned descriptor, then returns bin_dir + cache_key
```

- **STY-0006 produces** the typed, pinned `ResolvedPyPISource` — it does **not**
  create a venv or download an artifact.
- **Environments consumes** it: `EnvManager` calls `resolve_pypi_source` for a
  `pypi` hook, then runs `uv` to build a cached venv from
  `name==version --index-url <index_url>` (and, if `sha256` is present, can pass
  `--require-hashes` for supply-chain pinning). The `project`/`system` kinds it
  delegates to STY-0005's `resolve_source`.
- `resolve_source`'s existing `PyPISource` rejection message already points here
  ("delegated to Environments (STY-0006)") — this story fulfils that promise
  without changing `resolve_source`.

## Tasks

- [ ] TSK-001: **[config-schema; design-gate approval]** Add
  `extra_registries: dict[str, str]` (alias `extra-registries`, default empty) to
  `hooksmith.config.SourceSpec`, matching the already-documented reference; validate
  alias keys `[A-Za-z0-9_-]+` and non-empty URL values. Carved out so it can land
  independently if the gate prefers to split the schema change.
- [ ] TSK-002: **[new dependency; design-gate approval]** Add `packaging>=24` to
  `pyproject.toml` runtime `dependencies`. HTTP/index parsing stay on stdlib
  (`urllib`, `json`, `html.parser`) — **no** `httpx`/`requests`.
- [ ] TSK-003: Create `src/hooksmith/registry/` package with `__init__.py` facade
  exporting `resolve_pypi_source`, `ResolvedPyPISource`, `RegistryClient`,
  `UrllibRegistryClient`, `RegistryError` (set `__all__`, alphabetical).
- [ ] TSK-004: Add `src/hooksmith/registry/resolved_pypi_source.py` —
  `ResolvedPyPISource` frozen pydantic model (`kind`, `requirement`, `name`,
  `version`, `index_url`, `registry`; optional `sha256`/`url`/`filename`;
  `ConfigDict(frozen=True, extra="forbid")`).
- [ ] TSK-005: Add `src/hooksmith/registry/registry_error.py` —
  `RegistryError(ValueError)` with structured `requirement` / `index_url` /
  `reason` and the `cannot resolve '<req>' against <index>: <reason>` message.
- [ ] TSK-006: Add `src/hooksmith/registry/registry_client.py` — the
  `RegistryClient` Protocol (`fetch_project`) + a `ProjectPage`/file value object,
  and `UrllibRegistryClient` (stdlib `urllib`, PEP 691 `Accept` + PEP 503 HTML
  fallback, 404/network/malformed → mapped by the resolver).
- [ ] TSK-007: Add `src/hooksmith/registry/index_resolver.py` — alias → index-URL
  resolution against a `SourceSpec | None` (default vs `extra_registries`; unknown
  alias → `RegistryError`).
- [ ] TSK-008: **(Optional / deferrable — raise separately if descoped)** Add a
  config-layer cross-field validation surfacing an **undeclared registry alias**
  in a hook `from` as a `ConfigError` at `load_config` with `check.toml:line:col`
  (mirrors STY-0004's spec-error translation). If omitted, the undeclared alias
  surfaces as `RegistryError` at resolve time instead.
- [ ] TSK-009: Implement `resolve_pypi_source(source, sources, *, client=None,
  allow_prereleases=False) -> ResolvedPyPISource` in
  `src/hooksmith/registry/pypi_resolver.py` — the 8-step algorithm above
  (index resolve → requirement parse → fetch → enumerate → specifier/pre-release
  filter → yanked rules → select highest → build descriptor).
- [ ] TSK-010: Write `tests/unit/test_pypi_resolver.py` (≥ 15 tests, hermetic via a
  `FakeRegistryClient`, no network): default index; alias index; unknown alias;
  exact `==` pin; range select-highest; bare-name → latest; pre-release excluded
  by default; pre-release included when specifier/flag opts in; pre-release-only
  match; yanked excluded; yanked selectable via exact pin; package-not-found (404);
  no-version-satisfies; network error wrapped; malformed response; optional
  artifact fields populated; determinism (two calls equal); `RegistryError`
  message format.
- [ ] TSK-011: Write `tests/unit/test_registry_client.py` (client-level, loopback
  `http.server` or `urlopen` monkeypatch — still no public internet): PEP 691 JSON
  parse; PEP 503 HTML fallback parse; 404 handling; timeout/URLError surfacing.
- [ ] TSK-012: Write `tests/integration/test_pypi_resolution_acceptance.py`
  (3–5 tests, hermetic): `pypi:` against the default index → pinned
  `ResolvedPyPISource`; `pypi+alias:` against a configured `extra-registries` URL;
  unknown alias → `RegistryError`; `load_config` of a `pypi:` hook still succeeds
  with no `ConfigError` (proves network resolution is not run at load time).
- [ ] TSK-013: Add an "Resolving `pypi:` / `pypi+alias:` sources" subsection to
  `docs/config/reference.md § Source spec syntax` documenting `resolve_pypi_source`,
  `ResolvedPyPISource`, the alias→URL rules, the PEP 440/PEP 592 selection rules,
  and that registry failures are runtime (not config) errors. Also document the new
  `extra-registries` field where the `[sources]` table is described.

## Acceptance criteria

- [ ] AC-1: `resolve_pypi_source(PyPISource(requirement="ruff==0.4.9"), sources)`
  against a fake index carrying `0.4.9` returns
  `ResolvedPyPISource(name="ruff", version="0.4.9", index_url=<default>,
  registry=None, kind="pypi")`.
- [ ] AC-2: For a range (`ruff>=0.4,<1`) with `0.4.1`, `0.4.9`, `1.0.0` available,
  the **highest satisfying** version (`0.4.9`) is selected.
- [ ] AC-3: A bare name (`ruff`, empty specifier) selects the **latest** non-pre-release version.
- [ ] AC-4: `registry=None` resolves the index to `sources.default_registry` (or
  the built-in `https://pypi.org/simple` when `sources` is `None` / unset).
- [ ] AC-5: `registry="internal"` resolves the index to
  `sources.extra_registries["internal"]`.
- [ ] AC-6: An undeclared alias raises `RegistryError` whose `reason` names the
  alias and `[sources].extra-registries`, with `index_url is None`.
- [ ] AC-7: A package the index 404s on raises `RegistryError` (reason: package not
  found), never a crash.
- [ ] AC-8: A specifier no available version satisfies (`ruff>=99`) raises
  `RegistryError` (reason: no version satisfies).
- [ ] AC-9: A pre-release (`0.5.0rc1`) is **excluded** by default, **included**
  when the specifier opts in (`>=0.5.0rc1` / `==0.5.0rc1`) or `allow_prereleases=True`,
  and **selected** when only pre-releases satisfy the specifier.
- [ ] AC-10: A yanked release is excluded from a range match but **selectable** when
  pinned exactly (`==<yanked>`) and it is the only match (PEP 592).
- [ ] AC-11: A network failure (`URLError`/timeout) and a malformed index body each
  raise `RegistryError` (network wrapped via `raise … from`), never propagate a
  raw `urllib`/parse exception.
- [ ] AC-12: When artifact fields are enabled, `sha256` / `url` / `filename` reflect
  the selected version's chosen file (wheel preferred over sdist); they are `None`
  when unavailable — the resolution still succeeds on `name`+`version`+`index_url`.
- [ ] AC-13: Resolution performs **no** venv creation, **no** artifact download, and
  **no** install — it only queries the index and returns a descriptor (verifiable
  by the `FakeRegistryClient` recording only `fetch_project` calls).
- [ ] AC-14: Every unit test is hermetic — the default suite makes **no real network
  call** (the seam is injected); any real-PyPI test is `@pytest.mark.network` and
  skipped by default.
- [ ] AC-15: `resolve_pypi_source` is deterministic — for a fixed `(source, sources,
  fake index response)`, two calls return equal `ResolvedPyPISource` values (or raise
  the same `RegistryError`).
- [ ] AC-16: `RegistryError` subclasses `ValueError`; its message has the form
  `cannot resolve '<requirement>' against <index>: <reason>`.
- [ ] AC-17: A registry/resolution failure does **not** surface as `ConfigError` and
  is **not** raised from `load_config`; loading a `pypi:` hook succeeds — the error
  only appears when `resolve_pypi_source` is called. (If TSK-008 lands, an
  *undeclared alias* is the sole exception, caught at load time as `ConfigError`.)
- [ ] AC-18: `from hooksmith.registry import resolve_pypi_source, ResolvedPyPISource,
  RegistryClient, RegistryError` works.
- [ ] AC-19: `mypy --strict src/hooksmith/registry/` passes with no new errors; the
  `RegistryClient` Protocol and the `ResolvedPyPISource` model type cleanly.
- [ ] AC-20: The dependency delta is exactly `packaging>=24` (runtime); no HTTP
  client dependency is added.
- [ ] AC-21: `resolve_source` (STY-0005) is **unchanged** — a `PyPISource` still
  raises `SourceResolutionError` there; `hooksmith.sources` gains no network I/O.

## Notes

- **Package placement (architect to confirm):** `hooksmith.registry` is recommended
  over `hooksmith.sources.pypi_resolver` to keep the `sources` leaf pure/no-I/O —
  see § Where the new code lives.
- **Design-gate approvals required before implementation (two items):**
  (1) new runtime dependency `packaging>=24`; (2) config-schema change adding
  `extra_registries` to `SourceSpec`. Both are flagged here per core conventions
  ("flag any new dependency"; schema files are otherwise change-controlled).
- **Registry approach (LOCKED recommendation):** PEP 503 simple index + PEP 691
  JSON content negotiation, **not** the Warehouse JSON API — the JSON API is
  PyPI-only and would break `pypi+alias:` private registries.
- **Artifact fields:** recommend populating `sha256`/`url`/`filename` best-effort
  (they enable hash-pinned installs and cache explainability) but treating
  `name`+`version`+`index_url` as the load-bearing contract; authoritative
  platform-specific wheel selection stays with uv/Environments. Architect locks
  whether to populate now or defer.
- **PEP 508 markers/extras** in a `requirement` are out of scope; recommend
  rejecting them with a clear `RegistryError` rather than silently ignoring.
  Architect locks reject-vs-ignore.
- **Auth to private indexes** (tokens / `.netrc` / keyring) is a documented
  fast-follower; the `RegistryClient` seam is the extension point. v1 targets
  anonymous / pre-credentialed indexes.
- **Windows / non-network:** no filesystem or platform concerns here — this story
  is pure network + version math; the venv/platform concerns live in Environments.
- **Downstream:** the Environments feature's `EnvManager.resolve(hook)` consumes
  `ResolvedPyPISource` to build the uv venv; this story is the typed hand-off point
  named in STY-0005's `pypi` rejection message.
