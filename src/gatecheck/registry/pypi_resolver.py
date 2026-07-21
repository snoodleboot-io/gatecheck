"""resolve_pypi_source — pin a PyPISource to an exact distribution (BUILD-0006-ARCH §4).

Orchestrates the 8-step algorithm: resolve index → parse requirement → fetch project
page → enumerate candidate versions → specifier/pre-release filter → PEP 592 yanked
rules → select highest → build ``ResolvedPyPISource``. Depends on the ``RegistryClient``
Protocol (not the concrete impl) and on ``index_resolver`` — pure over its inputs given
an injected client (no venv creation, no download, no install).
"""

from __future__ import annotations

import urllib.error
from urllib.parse import urlsplit

from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import (
    InvalidSdistFilename,
    InvalidWheelFilename,
    canonicalize_name,
    parse_sdist_filename,
    parse_wheel_filename,
)
from packaging.version import Version

from gatecheck.config import SourceSpec
from gatecheck.registry.index_resolver import resolve_index_url
from gatecheck.registry.registry_client import (
    MalformedIndexResponse,
    PackageNotFound,
    ProjectFile,
    ProjectPage,
    RegistryClient,
    UrllibRegistryClient,
)
from gatecheck.registry.registry_error import RegistryError
from gatecheck.registry.resolved_pypi_source import ResolvedPyPISource
from gatecheck.sources import PyPISource

_SDIST_SUFFIXES = (".tar.gz", ".zip")


def resolve_pypi_source(
    source: PyPISource,
    sources: SourceSpec | None,
    *,
    client: RegistryClient | None = None,
    allow_prereleases: bool = False,
    offline: bool = False,
) -> ResolvedPyPISource:
    """Resolve ``source`` to a pinned ``ResolvedPyPISource`` by querying the index.

    ``client`` defaults to ``UrllibRegistryClient()`` (constructed inside the body,
    never a mutable default). Raises ``RegistryError`` for every failure domain
    (unknown alias, invalid requirement, markers/extras, package-not-found,
    no-version-satisfies, network, malformed index).

    When ``offline`` is true the index is **not** queried: the pin is derived locally
    and the requirement must carry a single exact ``==`` version (``RegistryError``
    otherwise). File metadata (``sha256``/``url``/``filename``) is unavailable offline.
    """
    index_url = _resolve_index(source, sources)
    if offline:
        return _resolve_offline(source, index_url)

    resolver_client = UrllibRegistryClient() if client is None else client
    requirement, canonical_name = _parse_requirement(source, index_url)
    page = _fetch(resolver_client, source, index_url, canonical_name)

    candidates = _enumerate_versions(page)
    selected = _select_version(
        requirement.specifier, candidates, source, index_url, canonical_name, allow_prereleases
    )
    files = candidates[selected]
    chosen = _choose_file(files)

    return ResolvedPyPISource(
        kind="pypi",
        requirement=source.requirement,
        name=str(canonical_name),
        version=str(selected),
        index_url=index_url,
        registry=source.registry,
        sha256=None if chosen is None else chosen.sha256,
        url=None if chosen is None else chosen.url,
        filename=None if chosen is None else chosen.filename,
        hashes=_all_hashes(files),
    )


def _all_hashes(files: list[ProjectFile]) -> tuple[str, ...]:
    """Every known sha256 across ``files``, in index order (files without one skipped).

    An install must accept any of the version's artifacts — the installer picks the
    wheel matching the current platform — so pinning only the representative file's
    hash makes the install fail everywhere else (BUG-0001).
    """
    return tuple(entry.sha256 for entry in files if entry.sha256)


def _resolve_index(source: PyPISource, sources: SourceSpec | None) -> str:
    """Resolve the index URL, re-wrapping an unknown-alias error with the requirement.

    The resolved URL must be ``http``/``https`` — a config-supplied ``file://`` (or
    other) scheme would make the client read local/non-HTTP resources, so it is
    rejected here before any network call (defense-in-depth).
    """
    try:
        index_url = resolve_index_url(source.registry, sources)
    except RegistryError as exc:
        raise RegistryError(source.requirement, exc.index_url, exc.reason) from None
    scheme = urlsplit(index_url).scheme
    if scheme not in ("http", "https"):
        raise RegistryError(
            source.requirement,
            index_url,
            f"unsupported index URL scheme '{scheme or '(none)'}' (only http/https allowed)",
        )
    return index_url


def _resolve_offline(source: PyPISource, index_url: str) -> ResolvedPyPISource:
    """Derive the pin from an exact ``==`` requirement without touching the index.

    Offline runs cannot enumerate index versions, so only a single exact pin is
    resolvable; a range/compatible/prefix requirement raises ``RegistryError``.
    """
    requirement, canonical_name = _parse_requirement(source, index_url)
    version = _exact_version(requirement.specifier)
    if version is None:
        raise RegistryError(
            source.requirement,
            index_url,
            "offline mode requires an exact pin (pypi:NAME==VERSION); "
            "run 'gatecheck sync' online first to warm the cache",
        )
    return ResolvedPyPISource(
        kind="pypi",
        requirement=source.requirement,
        name=str(canonical_name),
        version=version,
        index_url=index_url,
        registry=source.registry,
        sha256=None,
        url=None,
        filename=None,
    )


def _exact_version(specifier: SpecifierSet) -> str | None:
    """Return the normalized version of a single exact ``==`` pin, else ``None``.

    A prefix match (``==1.0.*``) or any non-``==``/multi-clause specifier is not an
    exact pin and yields ``None``.
    """
    specs = list(specifier)
    if len(specs) != 1:
        return None
    spec = specs[0]
    if spec.operator != "==" or spec.version.endswith(".*"):
        return None
    return str(Version(spec.version))


def _parse_requirement(source: PyPISource, index_url: str) -> tuple[Requirement, str]:
    """Parse the PEP 508 requirement; reject invalid specs and markers/extras."""
    try:
        requirement = Requirement(source.requirement)
    except InvalidRequirement as exc:
        raise RegistryError(source.requirement, index_url, f"invalid requirement: {exc}") from exc
    if requirement.marker is not None or requirement.extras:
        raise RegistryError(
            source.requirement, index_url, "requirement markers/extras are not supported"
        )
    return requirement, str(canonicalize_name(requirement.name))


def _fetch(client: RegistryClient, source: PyPISource, index_url: str, name: str) -> ProjectPage:
    """Fetch the project page, mapping client failure signals to RegistryError."""
    try:
        return client.fetch_project(index_url, name)
    except PackageNotFound as exc:
        raise RegistryError(
            source.requirement, index_url, f"package '{name}' not found on index"
        ) from exc
    except MalformedIndexResponse as exc:
        raise RegistryError(
            source.requirement, index_url, f"malformed index response from {index_url}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RegistryError(
            source.requirement, index_url, f"network error querying index: {exc}"
        ) from exc


def _enumerate_versions(page: ProjectPage) -> dict[Version, list[ProjectFile]]:
    """Group each parseable file under its release ``Version`` (ignore non-dist files)."""
    candidates: dict[Version, list[ProjectFile]] = {}
    for entry in page.files:
        version = _file_version(entry.filename)
        if version is None:
            continue
        candidates.setdefault(version, []).append(entry)
    return candidates


def _file_version(filename: str) -> Version | None:
    """Derive a file's ``Version`` from its wheel/sdist name; ``None`` for neither."""
    try:
        if filename.endswith(".whl"):
            return parse_wheel_filename(filename)[1]
        if filename.endswith(_SDIST_SUFFIXES):
            return parse_sdist_filename(filename)[1]
    except (InvalidWheelFilename, InvalidSdistFilename):
        return None
    return None


def _select_version(
    specifier: SpecifierSet,
    candidates: dict[Version, list[ProjectFile]],
    source: PyPISource,
    index_url: str,
    name: str,
    allow_prereleases: bool,
) -> Version:
    """Filter by specifier + pre-release + PEP 592 yanked rules; return the highest.

    ``name`` is the already-canonicalized project name (threaded from the caller so
    the no-version error message needs no redundant requirement re-parse).
    """
    prereleases = True if allow_prereleases else None
    matched = list(specifier.filter(candidates.keys(), prereleases=prereleases))

    non_yanked = [v for v in matched if not _version_yanked(candidates[v])]
    if non_yanked:
        selectable = non_yanked
    elif matched and _is_exact_pin(specifier):
        selectable = matched
    else:
        selectable = []

    if not selectable:
        raise RegistryError(
            source.requirement,
            index_url,
            f"no version of '{name}' satisfies '{specifier}'",
        )
    return max(selectable)


def _version_yanked(files: list[ProjectFile]) -> bool:
    """A release is yanked when it has files and all of them are yanked (PEP 592)."""
    return bool(files) and all(entry.yanked for entry in files)


def _is_exact_pin(specifier: SpecifierSet) -> bool:
    """True when the specifier pins an exact version (``==`` / ``===``)."""
    return any(spec.operator in ("==", "===") for spec in specifier)


def _choose_file(files: list[ProjectFile]) -> ProjectFile | None:
    """Pick one representative file for the best-effort fields (wheel preferred)."""
    wheel = next((entry for entry in files if entry.filename.endswith(".whl")), None)
    if wheel is not None:
        return wheel
    sdist = next((entry for entry in files if entry.filename.endswith(_SDIST_SUFFIXES)), None)
    if sdist is not None:
        return sdist
    return files[0] if files else None
