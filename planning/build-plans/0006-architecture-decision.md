---
id: BUILD-0006-ARCH
title: Architecture decision for STY-0006 (resolve pypi / pypi+alias sources against a registry)
parent: BUILD-0006
target_story: STY-0006
status: Locked
date: 2026-07-05
---

# BUILD-0006-ARCH: Resolve `pypi:` / `pypi+alias:` specs against a registry to a pinned distribution

> **LOCKED CONTRACT.** The code / test / review lanes consume this document.
> Any change requires re-opening BUILD-0006 §1.

> **Design gate (APPROVED, build to these):**
> 1. Add `packaging>=24` as a runtime dependency (PEP 440 `SpecifierSet`/`Version`,
>    PEP 508 `Requirement`, filename parsers, `canonicalize_name`).
> 2. Add `extra_registries` to the `[sources]` config schema (alias→index-URL map).
> 3. HTTP via stdlib `urllib.request`; index format PEP 503 simple + PEP 691 JSON
>    content negotiation — **not** the Warehouse JSON API.

---

## §1 Placement — new leaf package `gatecheck.registry` (LOCKED)

### Decision

The network resolver lands in a **new leaf package** `src/gatecheck/registry/`,
**not** inside `gatecheck.sources`. `gatecheck.sources` was built by STY-0004/0005
as a **pure, dependency-light, no-I/O leaf** (its ACs assert "no network, no
subprocess, no writes"). STY-0006 is the opposite concern: it performs network
I/O (`urllib`) and depends on `packaging`. Landing it in `sources` would
contradict that package's established character and pull a network dependency
into a leaf that the parser/resolver keep pure.

This yields a clean three-way split of FEAT-0002 + Environments:

- **`gatecheck.sources`** — classify a `from` spec (`parse_source`) and locate the
  local kinds (`resolve_source`). Pure, no I/O. **Unchanged by this story.**
- **`gatecheck.registry`** — query an index and pin a `pypi:` requirement to a
  concrete distribution. Network + `packaging`. **New, this story.**
- **`gatecheck.env`** — build/cache the uv venv from the pinned descriptor
  (Environments). Consumes this story's output. Not built here.

### Justification

1. **Character preservation.** `sources` imports only stdlib + `pydantic` and no
   sibling package. Introducing `urllib`/`packaging`/network there would break the
   "pure leaf" invariant STY-0005 §7 locked.
2. **STY-0005 contract stays verbatim.** `resolve_source`'s `PyPISource` branch
   still raises `SourceResolutionError("pypi source resolution is delegated to
   Environments (STY-0006), not handled here")`. The `pypi` network path is a
   **separate entry point** — `registry.resolve_pypi_source` — that the
   Environments `EnvManager` calls directly. **`resolve_source` is not touched**
   (AC-21).
3. **Different failure domain.** Registry failures (unknown alias / 404 / no-match
   / network / malformed) carry `requirement`/`index_url` diagnostics, not
   `tool`/`kind`. A dedicated package + error type (SRP) keeps the two domains
   apart.
4. **Import direction stays acyclic.** `registry` imports `gatecheck.sources`
   (`PyPISource`) and `gatecheck.config` (`SourceSpec`) — both already leaves.
   Nothing imports `registry` back. See §8.

---

## §2 Module layout — `src/gatecheck/registry/` (LOCKED)

One class / function-group per file (core conventions: filename = snake_case of
the class). Names follow the story's file table verbatim.

| File | Status | Single responsibility |
|---|---|---|
| `src/gatecheck/registry/resolved_pypi_source.py` | **NEW** | `ResolvedPyPISource` frozen pydantic model (the pinned descriptor). |
| `src/gatecheck/registry/registry_error.py` | **NEW** | `RegistryError(ValueError)` with structured `requirement` / `index_url` / `reason`. |
| `src/gatecheck/registry/registry_client.py` | **NEW** | `RegistryClient` Protocol (the network seam) + `ProjectPage` / `ProjectFile` value objects + fetch-failure signals (`PackageNotFound`, `MalformedIndexResponse`) + `UrllibRegistryClient` default impl (stdlib `urllib`, PEP 691 JSON + PEP 503 HTML fallback). |
| `src/gatecheck/registry/index_resolver.py` | **NEW** | `resolve_index_url(...)` — alias → index-URL resolution against a `SourceSpec \| None`. No class. |
| `src/gatecheck/registry/pypi_resolver.py` | **NEW** | `resolve_pypi_source(...) -> ResolvedPyPISource` + private version-selection helpers. No class. |
| `src/gatecheck/registry/__init__.py` | **NEW** | Facade — export the public symbols; set `__all__`. |
| `src/gatecheck/config/source_spec.py` | **EDIT** | Add `extra_registries` field (§7). Carved as TSK-001; may land as its own reviewable commit. |

### Why split the client, the index resolver, and the pypi resolver

- **`registry_client.py`** is the **only** module that touches the network. It is
  the injectable seam (§5) — isolating it means the entire default test suite runs
  offline against a `FakeRegistryClient`, and the real `UrllibRegistryClient` is
  the single place HTTP status / content-negotiation / parse logic lives.
- **`index_resolver.py`** is a **pure** alias→URL function with **no network** and
  no `packaging` dependency. Keeping it separate lets it (and the unknown-alias
  error path, AC-6) be unit-tested without any fake client, and keeps
  `pypi_resolver` focused on version math.
- **`pypi_resolver.py`** orchestrates the 8-step algorithm (§4): it owns
  requirement parsing, version enumeration, specifier/pre-release/yanked filtering,
  and descriptor construction — the `packaging` logic. It depends on the client
  Protocol (not the concrete impl) and on `index_resolver`.

### `__init__.py` exports / `__all__` (LOCKED)

Alphabetical, uppercase before lowercase (matching `gatecheck.sources` §2 style).

```python
"""Public facade for gatecheck.registry (BUILD-0006-ARCH §2)."""
from __future__ import annotations

from gatecheck.registry.pypi_resolver import resolve_pypi_source
from gatecheck.registry.registry_client import (
    ProjectFile,
    ProjectPage,
    RegistryClient,
    UrllibRegistryClient,
)
from gatecheck.registry.registry_error import RegistryError
from gatecheck.registry.resolved_pypi_source import ResolvedPyPISource

__all__ = [
    "ProjectFile",
    "ProjectPage",
    "RegistryClient",
    "RegistryError",
    "ResolvedPyPISource",
    "UrllibRegistryClient",
    "resolve_pypi_source",
]
```

AC-18 requires `from gatecheck.registry import resolve_pypi_source,
ResolvedPyPISource, RegistryClient, RegistryError` to work — satisfied above.
`ProjectPage` / `ProjectFile` / `UrllibRegistryClient` are also exported so test
lanes can construct fixtures / the concrete client through the facade.

---

## §3 Model spec — `ResolvedPyPISource` (exact types, LOCKED)

Frozen pydantic `BaseModel`, mirroring the STY-0004 source models exactly.

```python
# resolved_pypi_source.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResolvedPyPISource(BaseModel):
    """A pypi source pinned to an exact version against a known index (BUILD-0006-ARCH §3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pypi"] = "pypi"
    requirement: str
    name: str
    version: str
    index_url: str
    registry: str | None = None
    sha256: str | None = None
    url: str | None = None
    filename: str | None = None
```

| Field | Type | Meaning |
|---|---|---|
| `kind` | `Literal["pypi"] = "pypi"` | Discriminator, consistent with `PyPISource`. |
| `requirement` | `str` | The original requirement text (`source.requirement`), echoed back. |
| `name` | `str` | The **canonicalized** project name (`packaging.utils.canonicalize_name`). |
| `version` | `str` | The **selected** exact version, `str(Version)`, e.g. `"0.4.9"`. |
| `index_url` | `str` | The resolved index URL the version was pinned against. |
| `registry` | `str \| None` | The `[sources]` alias used (`source.registry`), or `None` for the default. |
| `sha256` | `str \| None` | *(best-effort)* hash of the chosen file, from the PEP 503/691 file entry. `None` when unavailable. |
| `url` | `str \| None` | *(best-effort)* download URL of the chosen file. `None` when unavailable. |
| `filename` | `str \| None` | *(best-effort)* filename of the chosen file. `None` when unavailable. |

### Populate-now vs defer decision — **POPULATE `sha256` / `url` / `filename` NOW, best-effort** (LOCKED)

The three optional artifact fields are **populated now**, best-effort, `None` when
unavailable. Rationale:

- They come **for free** from the same simple-index entry the resolver already
  parses to enumerate versions — no extra request, no extra parse pass.
- They enable downstream **supply-chain hash-pinning** (Environments can pass
  `--require-hashes` when `sha256` is present) and **cache/explainability**, which
  are stated PRD goals.
- Populating now keeps the boundary forward-compatible without committing
  Environments to anything: the **load-bearing contract is `name` + `version` +
  `index_url`** (enough for `install name==version --index-url <index_url>`). The
  optional fields are advisory metadata, **not authoritative artifact selection.**
- **Authoritative, platform/interpreter-specific wheel selection stays with
  uv/Environments** (it depends on the target env being built, which this story
  does not own — see §10). This story picks *one* representative file per selected
  version (wheel preferred over sdist) purely to fill the best-effort fields;
  if the version has no parseable file entry, all three are `None` and resolution
  still succeeds on `name`+`version`+`index_url` (AC-12).

No `kind`-discriminated union membership: `ResolvedPyPISource` is an **output**
value object, not a member of `ParsedSource`.

---

## §4 `resolve_pypi_source` — signature, algorithm & error table (LOCKED)

### Signature

```python
# pypi_resolver.py
from gatecheck.config import SourceSpec
from gatecheck.registry.registry_client import RegistryClient
from gatecheck.registry.resolved_pypi_source import ResolvedPyPISource
from gatecheck.sources import PyPISource


def resolve_pypi_source(
    source: PyPISource,
    sources: SourceSpec | None,
    *,
    client: RegistryClient | None = None,
    allow_prereleases: bool = False,
) -> ResolvedPyPISource: ...
```

> **Naming (LOCKED):** the public function is **`resolve_pypi_source`** (matching
> the story's AC-1/TSK-009 and `resolve_source`'s reference message), landing in
> **`pypi_resolver.py`**. (The design-gate brief's shorthand `resolve_pypi` in
> `resolver.py` is reconciled to the story's names — see § Deviations.)

- **`source`** — the `PyPISource` from `parse_source(hook.from_)`, carrying the
  verbatim `requirement` and the optional registry `alias` (`registry`).
- **`sources`** — the parsed `[sources]` table (`GatecheckConfig.sources`, may be
  `None`). Supplies `default_registry` and the new `extra_registries` alias map.
- **`client`** — the injectable network seam (§5). `None` → `UrllibRegistryClient()`
  (constructed **inside** the body, never a mutable default). Tests pass a fake.
- **`allow_prereleases`** — caller override for pre-release selection (default
  `False`). The specifier itself may still opt in per PEP 440.

Defaults are resolved **inside** the function body (`client = UrllibRegistryClient()
if client is None else client`) — never as mutable default arguments (mirrors
STY-0005 §4).

### Algorithm (precise, deterministic given a fixed index response)

1. **Resolve the index URL** — delegate to `index_resolver.resolve_index_url(
   source.registry, sources)`:
   - `source.registry is None` → `sources.default_registry` if set, else the
     **built-in default** `https://pypi.org/simple` (used when `sources` is `None`
     or `default_registry` unset). (AC-4)
   - `source.registry == "<alias>"` → `sources.extra_registries["<alias>"]`. (AC-5)
   - alias not present in `extra_registries` (or `sources is None`) → raise
     `RegistryError(requirement, index_url=None, reason=<unknown alias>)`. (AC-6)
   The resolved URL's trailing slash is normalized (strip one trailing `/`) so
   `{index_url}/{name}/` is well-formed.
2. **Parse the requirement** — `packaging.requirements.Requirement(source.requirement)`:
   derive the project name and `SpecifierSet`. This is where PEP 508 parsing finally
   happens (deferred verbatim from STY-0004). A bare name (`ruff`) → empty specifier.
   - **Malformed requirement** (`InvalidRequirement`) → `RegistryError(reason=invalid
     requirement)` (wrap via `from`).
   - **Markers / extras present** → **REJECT** with `RegistryError(reason=markers/
     extras not supported)` (LOCKED reject-not-ignore — avoids silent surprises;
     story recommendation). Detect via `req.marker is not None` or `req.extras`.
   - `canonical_name = packaging.utils.canonicalize_name(req.name)`.
3. **Fetch the project page** — `client.fetch_project(index_url, canonical_name)`
   (`GET {index_url}/{canonical_name}/`, PEP 691 `Accept` header). The resolver
   wraps the client's failure signals (§5):
   - `PackageNotFound` → `RegistryError(reason=package not found)`. (AC-7)
   - `MalformedIndexResponse` → `RegistryError(reason=malformed index response)`.
   - `(urllib.error.URLError, TimeoutError, OSError)` → `RegistryError(reason=
     network error querying index)` **via `raise … from`**. (AC-11)
4. **Enumerate candidate versions** — from `page.files`, derive each file's
   `Version` with `packaging.utils.parse_wheel_filename` / `parse_sdist_filename`
   (dispatch on extension; ignore files whose name parses to neither — e.g. eggs).
   Record per file: `version`, `yanked` flag (PEP 592), `sha256`, `url`,
   `filename`. Build `version → list[ProjectFile]`.
5. **Filter by specifier + pre-release rules** — `SpecifierSet.filter(versions,
   prereleases=_prereleases_flag)`. Pre-releases are excluded **unless**: (a) the
   specifier explicitly permits them, (b) `allow_prereleases=True`, or (c) *only*
   pre-releases satisfy the specifier — matching pip/`packaging` semantics.
   `_prereleases_flag = True if allow_prereleases else None` (letting `packaging`
   apply rule (a)/(c) when `None`). (AC-9)
6. **Apply yanked rules (PEP 592)** — exclude yanked versions **unless** the
   specifier pins that exact version (`== X`) **and** it is the only surviving
   match — then it is selectable. (AC-10)
7. **Select the highest** remaining `Version`. None remain → `RegistryError(reason=
   no version of '<name>' satisfies '<specifier>')`. (AC-8) For the selected
   version, pick its file for the optional fields: **prefer a wheel** (`.whl`), else
   the sdist (`.tar.gz`); take that file's `sha256` / `url` / `filename`. If no
   file entry is usable, all three stay `None` (AC-12).
8. **Return** `ResolvedPyPISource(kind="pypi", requirement=source.requirement,
   name=str(canonical_name), version=str(selected_version), index_url=index_url,
   registry=source.registry, sha256=…, url=…, filename=…)`.

**Determinism (AC-15):** given the same `(source, sources, index response)` the
function returns an equal `ResolvedPyPISource` (or raises the same `RegistryError`).
The only non-determinism is the live index; the injected `client` makes the
function pure over its inputs in tests. **No venv creation, no artifact download,
no install** anywhere (AC-13) — the function only calls `client.fetch_project`.

### Error table (`RegistryError` reasons — LOCKED)

| Case | `index_url` | `reason` (illustrative) | AC |
|---|---|---|---|
| Unknown registry alias (`pypi+internal:`, no `internal` in `extra-registries`) | `None` | `unknown registry alias 'internal' (not declared in [sources].extra-registries)` | AC-6 |
| Invalid PEP 508 requirement | resolved URL | `invalid requirement: <detail>` | — |
| Markers / extras present in requirement | resolved URL | `requirement markers/extras are not supported` | — |
| Package not found (index 404 for the project) | resolved URL | `package '<name>' not found on index` | AC-7 |
| No version satisfies the specifier | resolved URL | `no version of '<name>' satisfies '<specifier>'` | AC-8 |
| Network / timeout (`URLError`, `TimeoutError`, `OSError`) | resolved URL | `network error querying index: <detail>` (`raise … from`) | AC-11 |
| Malformed index response (unparseable JSON/HTML) | resolved URL | `malformed index response from <url>` | AC-11 |

All produce a message of the form `cannot resolve '<requirement>' against <index>:
<reason>` (AC-16). When `index_url is None`, the message uses the literal
`<unresolved index>` placeholder (unknown-alias case).

---

## §5 `RegistryClient` Protocol + fetch-failure seam (LOCKED)

The network boundary is a **single injectable `typing.Protocol`** so the default
suite is fully offline (AC-14) and the function is a pure function of its inputs in
tests (mirrors STY-0005's injectable `environ` / `workspace_root`).

```python
# registry_client.py
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict


class ProjectFile(BaseModel):
    """One file entry from a simple-index project page."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: str
    url: str | None = None
    sha256: str | None = None
    yanked: bool = False


class ProjectPage(BaseModel):
    """A parsed simple-index project page: the files available for a project."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    files: tuple[ProjectFile, ...] = ()


class PackageNotFound(Exception):
    """Raised by a RegistryClient when the index has no such project (HTTP 404)."""


class MalformedIndexResponse(Exception):
    """Raised by a RegistryClient when the project page body cannot be parsed."""


class RegistryClient(Protocol):
    def fetch_project(self, index_url: str, name: str) -> ProjectPage: ...
```

- **Single method:** `fetch_project(index_url: str, name: str) -> ProjectPage`.
  `name` is already canonicalized by the resolver (step 2). The client performs
  `GET {index_url}/{name}/` and returns the parsed `ProjectPage`.
- **Failure contract (documented, part of the seam):** the client raises
  `PackageNotFound` on 404, `MalformedIndexResponse` on an unparseable body, and
  lets `urllib.error.URLError` / `TimeoutError` / `OSError` propagate for network
  failures. The client does **not** raise `RegistryError` (it lacks the
  `requirement`); the **resolver** catches these and wraps them with requirement +
  index context (§4 step 3). A `FakeRegistryClient` raises the same three signals
  to exercise every error path offline.
- **`UrllibRegistryClient` (default impl):** stdlib `urllib.request` only. Sends
  `Accept: application/vnd.pypi.simple.v1+json` (PEP 691). If the response is JSON,
  parse via stdlib `json` into `ProjectPage`. If a registry serves HTML (PEP 503),
  fall back to a stdlib `html.parser.HTMLParser` subclass that collects `<a>`
  anchors (href → `url`, text → `filename`, `data-yanked` → `yanked`, the
  `#sha256=` URL fragment → `sha256`). Maps HTTP 404 → `PackageNotFound`; JSON/HTML
  parse failure → `MalformedIndexResponse`; leaves `URLError`/timeout to propagate.
  A short connect/read timeout is passed to `urlopen`.

Why value objects (not raw dicts): `ProjectPage` / `ProjectFile` are frozen
pydantic models so the seam is typed end-to-end (AC-19) and fixtures are explicit.

---

## §6 `RegistryError(ValueError)` (LOCKED)

```python
# registry_error.py
from __future__ import annotations


class RegistryError(ValueError):
    """Raised by resolve_pypi_source when a pypi source cannot be pinned (BUILD-0006-ARCH §6).

    Mirrors SourceResolutionError's shape — subclasses ValueError, carries
    structured fields, is location-free. A registry failure is a
    runtime/environment condition (network / index state), NOT a check.toml syntax
    error, so it does NOT map to ConfigError (§7 / AC-17).
    """

    requirement: str
    index_url: str | None
    reason: str

    def __init__(self, requirement: str, index_url: str | None, reason: str) -> None:
        self.requirement = requirement
        self.index_url = index_url
        self.reason = reason
        loc = index_url if index_url is not None else "<unresolved index>"
        super().__init__(f"cannot resolve '{requirement}' against {loc}: {reason}")
```

- Subclasses `ValueError` (consistent with `SourceSpecError` /
  `SourceResolutionError` / `ConfigError`). (AC-16)
- `index_url` is `None` **only** for the unknown-alias case (no URL resolved yet);
  every other reason carries the resolved URL.
- New type (not reuse `SourceResolutionError`): SRP — different failure domain,
  different diagnostic fields (`requirement`/`index_url` vs `tool`/`kind`).

---

## §7 Config schema change — `SourceSpec.extra_registries` (LOCKED)

### Exact edit to `src/gatecheck/config/source_spec.py`

```python
"""SourceSpec model — `[sources]` table (BUILD-0001-ARCH §3.1, BUILD-0006-ARCH §7)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALIAS_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]+")


class SourceSpec(BaseModel):
    """Pydantic model for the `[sources]` table in check.toml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    default_registry: str | None = Field(default=None, alias="default-registry", min_length=1)
    extra_registries: dict[str, str] = Field(default_factory=dict, alias="extra-registries")

    @field_validator("extra_registries")
    @classmethod
    def _check_extra_registries(cls, value: dict[str, str]) -> dict[str, str]:
        for alias, url in value.items():
            if _ALIAS_RE.fullmatch(alias) is None:
                raise ValueError(f"registry alias '{alias}' must match [A-Za-z0-9_-]+")
            if not url:
                raise ValueError(f"registry '{alias}' has an empty index URL")
        return value
```

- **Type:** `dict[str, str]` (alias → index-URL), default empty. Matches AC-5
  (`sources.extra_registries["internal"]`) and the approved design gate
  ("alias→index-URL map").
- **TOML alias:** `extra-registries` (`populate_by_name=True` already set, so both
  `extra-registries` in TOML and `extra_registries` in Python construct). Hyphenated
  key handled exactly as `default-registry` / `pass-files` / `depends-on` elsewhere.
- **Validation:** alias charset `[A-Za-z0-9_-]+` (identical to the parser's
  `_ALIAS_RE`, so a `pypi+<alias>:` that parses can match a declared registry) and
  non-empty URL. Raising `ValueError` inside the validator means an invalid
  `[sources]` surfaces through the **existing** pydantic → `ConfigError`
  translation in `load_config` with `check.toml:line:col` — no new config plumbing.
- **TOML shape (LOCKED):** a `dict` deserializes from a TOML **table**, e.g.
  ```toml
  [sources.extra-registries]
  internal = "https://pkg.example.com/simple"
  ```
  or the inline form `extra-registries = { internal = "https://pkg.example.com/simple" }`.

### `dump_config` round-trip (STY-0003) — confirmed intact

`dumper._build_document` writes `sources` by iterating `sources_data.items()` and
`src_table.add(key, value)`. With `model_dump(by_alias=True, exclude_none=True,
exclude_defaults=True)`, an **empty** `extra_registries` is omitted (default →
excluded), so **existing configs and their round-trip are unchanged**. A non-empty
`extra_registries` dumps as `extra-registries = { alias = "url" }` (tomlkit renders
a `dict` value as an inline table), which re-parses back into the same `dict[str,
str]`. Round-trip preserved; no existing config test breaks (the field is optional
with an empty default).

---

## §8 ConfigError mapping — undeclared-alias validator is OUT of scope (LOCKED)

**Decision: TSK-008 (a config-time cross-field validator surfacing an undeclared
registry alias as `ConfigError` at `load_config`) is OUT of scope for this build.**

Rationale:

- **Keeps the slice minimal and cohesive.** The story's core value is the network
  resolver; a cross-field `hook.from_` alias vs `[sources].extra-registries`
  validator is a *separate* config-layer concern that would add another
  `_error_translator` pass and its own tests for marginal benefit.
- **The mistake is still caught — with a clear, typed error.** Without TSK-008, an
  undeclared alias surfaces as `RegistryError` (`index_url=None`, reason names the
  alias and `[sources].extra-registries`) at resolve time (AC-6). Nothing is
  silently wrong.
- **The resolver stays location-free** (mirrors STY-0005 §5): the network path
  never fabricates a `check.toml:line:col`. Only the **unknown-alias** case has any
  config-time meaning at all; the other reasons (404 / no-match / network /
  malformed) are unambiguously runtime and never map to `ConfigError`.

Consequently **AC-17 holds unconditionally in this build**: a registry/resolution
failure does **not** surface as `ConfigError` and is **not** raised from
`load_config`; loading a `pypi:` hook succeeds (network resolution is not run at
load time). If a future story lands TSK-008, an *undeclared alias* becomes the sole
load-time exception — but that is explicitly deferred here.

`load_config` is **unchanged** by this build.

---

## §9 Dependency + `mypy --strict` strategy (LOCKED)

- **New runtime dependency (design-gate approved):** add **`packaging>=24`** to
  `[project].dependencies` in `pyproject.toml` (TSK-002). It is the de-facto
  standard for PEP 440/508 semantics (pip/uv/setuptools depend on it). Dependency
  delta is **exactly one** package (AC-20). HTTP + index parsing stay on stdlib
  (`urllib`, `json`, `html.parser`) — **no** `httpx`/`requests`.
- **mypy for `packaging`:** `packaging` **ships `py.typed`** (PEP 561, confirmed on
  the local install) and is fully typed. **No mypy override is needed** — unlike
  the `gatecheck_core` Rust extension (which has no stubs and carries an
  `ignore_missing_imports` override). `SpecifierSet` / `Version` / `Requirement` /
  `canonicalize_name` / `parse_wheel_filename` / `parse_sdist_filename` all type
  cleanly under `--strict`.
- **`from __future__ import annotations`** in every new module; every function and
  the `RegistryClient` Protocol / `ResolvedPyPISource` / `ProjectPage` /
  `ProjectFile` models fully annotated. Target: `mypy --strict
  src/gatecheck/registry/` passes with **no new errors and no `# type: ignore`**
  (AC-19). `parse_wheel_filename` returns a 4-tuple whose first element is a
  `NormalizedName` and `parse_sdist_filename` a 2-tuple — both destructured with
  explicit types; no `Any` leaks.
- **pytest `network` marker (implementation note):** `--strict-markers` is enabled
  and only `slow` / `integration` are registered. The optional real-PyPI smoke test
  (AC-14, skipped by default) uses `@pytest.mark.network`, so the `network` marker
  must be **registered** in `[tool.pytest.ini_options].markers` — a one-line
  `pyproject.toml` edit that rides with TSK-002. (Alternative: reuse the existing
  `integration` marker; **locked choice is to register `network`** to match the
  story's AC-14 wording and keep the hermetic default run explicit.)

---

## §10 Hermetic testing seam (LOCKED)

- **Injected `RegistryClient`** is the whole seam: `resolve_pypi_source(...,
  client=None)` defaults to `UrllibRegistryClient()`; tests pass a
  `FakeRegistryClient` returning canned `ProjectPage` fixtures (built from captured
  PEP 691 JSON / PEP 503 HTML snippets) and raising `PackageNotFound` /
  `MalformedIndexResponse` / `URLError` to drive every error path. **No
  monkeypatching of `urllib`** in the resolver suite — the seam is a parameter
  (cleaner + `mypy --strict` friendly).
- **Default suite is fully offline / deterministic** (AC-14, AC-15). AC-13 is
  verified by a `FakeRegistryClient` that records only `fetch_project` calls (no
  venv / download / install surface exists to call).
- **`UrllibRegistryClient` is tested against a loopback `http.server`** (stdlib) or
  a `urlopen` monkeypatch — never the public internet — covering PEP 691 JSON
  parse, PEP 503 HTML fallback parse, 404 → `PackageNotFound`, timeout/`URLError`
  surfacing (TSK-011).
- **One optional real-PyPI smoke test** may be `@pytest.mark.network` and **skipped
  by default** so the CI gate stays hermetic (§9 marker note). **Locked: include it
  but keep it skipped by default.**

Test files (per story): `tests/unit/test_pypi_resolver.py` (≥15 hermetic tests via
`FakeRegistryClient`), `tests/unit/test_registry_client.py` (client-level, loopback
/ monkeypatch), `tests/integration/test_pypi_resolution_acceptance.py` (3–5
hermetic acceptance tests, incl. proof that `load_config` of a `pypi:` hook
succeeds with no `ConfigError`).

---

## §11 Import direction / no cycle (LOCKED)

- `gatecheck.registry` imports: stdlib (`urllib`, `json`, `html.parser`, `re`,
  `typing`), `pydantic`, `packaging`, and — from **other leaves** —
  `gatecheck.sources.PyPISource` and `gatecheck.config.SourceSpec`.
- Nothing imports `gatecheck.registry` back (it is a new leaf consumed later by
  `gatecheck.env` / the runner). **No cycle.**
- **`gatecheck.sources` gains no network I/O** and is not modified (AC-21).
  `gatecheck.config` gains only the `extra_registries` field (§7); no import of
  `registry`.
- Import direction: `config` → `sources` (existing); `registry` → `sources` +
  `config`; `env`/runner → `registry` (later). Acyclic.

---

## §12 Explicitly OUT of scope (re-stated)

- **Venv creation / artifact download / installation** — Environments (uv-backed).
  This story returns a descriptor only.
- **Dependency-graph / transitive resolution and hash-pinning the closure** — uv's
  job at env-build time. This story pins the *single* hook requirement.
- **Platform/interpreter-specific wheel selection** — uv's job; the best-effort
  `sha256`/`url`/`filename` pick one representative file (wheel-preferred), not the
  target-platform wheel (§3).
- **Caching the registry response / resolved version** — Cache feature. Each call
  queries live (the fake makes tests deterministic).
- **Authentication to private indexes** (tokens / `.netrc` / keyring) — documented
  fast-follower; the `RegistryClient` seam is the extension point. v1 targets
  anonymous / pre-credentialed indexes.
- **PEP 508 markers / extras** in a requirement — **rejected** with a clear
  `RegistryError` (§4 step 2), not silently ignored.
- **The undeclared-alias `ConfigError` validator (TSK-008)** — deferred (§8);
  undeclared alias surfaces as `RegistryError` at resolve time.
- **`project` / `system` / `UnsupportedSource` kinds** — owned by STY-0005's
  `resolve_source`, unchanged. **`resolve_source` is not touched** (AC-21).
- **The Warehouse JSON API** — rejected; PEP 503 + PEP 691 only (design gate).

---

## Appendix

- Story:
  `planning/features/FEAT-0002-source-resolution/stories/STY-0006-resolve-pypi-registry-specs.md`
- Feature: `planning/features/FEAT-0002-source-resolution/feature.md`
- Build charter: `planning/build-plans/0006-charter.md`
- Predecessor architecture documents:
  - `0005-architecture-decision.md` — `SourceResolutionError` shape, injected-seam
    idiom, frozen-model idiom, `__all__` ordering, "does NOT map to `ConfigError`"
    reasoning (mirrored here for `RegistryError`).
  - `0004-architecture-decision.md` — `gatecheck.sources` package, `PyPISource`
    model, `ParsedSource` union, import direction.
- Consumed (unchanged) code:
  - `src/gatecheck/sources/pypi_source.py` — `PyPISource(requirement, registry)`
    (the resolver's input).
  - `src/gatecheck/sources/resolver.py` — `resolve_source`'s `PyPISource` rejection
    message points here; **not modified** (AC-21).
  - `src/gatecheck/config/gatecheck_config.py` — `GatecheckConfig.sources`.
  - `src/gatecheck/config/dumper.py` — `dump_config` round-trip (§7).
  - `src/gatecheck/config/_error_translator.py` / `loader.py` — pydantic →
    `ConfigError` translation the `extra_registries` validator rides on (§7); no
    new pass added (§8 defers TSK-008).
- Docs (updated by TSK-013, not this doc):
  - `docs/config/reference.md § [sources]` — the `extra-registries` example must be
    corrected from "list of `{alias = url}`" to the `dict`/table form (see §
    Deviations in the charter).
- New code (red): `src/gatecheck/registry/{__init__,resolved_pypi_source,
  registry_error,registry_client,index_resolver,pypi_resolver}.py`;
  edit `src/gatecheck/config/source_spec.py`.
- New tests (red): `tests/unit/test_pypi_resolver.py`,
  `tests/unit/test_registry_client.py`,
  `tests/integration/test_pypi_resolution_acceptance.py`.
