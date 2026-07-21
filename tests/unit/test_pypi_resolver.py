"""Unit tests for gatecheck.registry.resolve_pypi_source (STY-0006 / TSK-010).

Contract under test is LOCKED by
``planning/build-plans/0006-architecture-decision.md``:

- §3: frozen pydantic ``ResolvedPyPISource`` (``kind`` / ``requirement`` / ``name``
  / ``version`` / ``index_url`` / ``registry`` / best-effort ``sha256`` / ``url`` /
  ``filename``).
- §4: ``resolve_pypi_source`` signature, the 8-step algorithm, and the EXACT
  ``RegistryError`` reason table (assertions here pin the LOCKED text so any code
  drift fails).
- §5: the ``RegistryClient`` Protocol seam + ``ProjectPage`` / ``ProjectFile``
  value objects + the ``PackageNotFound`` / ``MalformedIndexResponse`` fetch-failure
  signals.
- §6: ``RegistryError(ValueError)`` with message
  ``cannot resolve '<requirement>' against <index>: <reason>``.

Every test is fully HERMETIC (AC-14): the network boundary is a dependency-injected
``FakeRegistryClient`` returning canned ``ProjectPage`` fixtures. No test touches
the network and none monkeypatches ``urllib``. AAA structure throughout.
"""

from __future__ import annotations

from urllib.error import URLError

import pydantic
import pytest

from gatecheck.config import SourceSpec
from gatecheck.registry import (
    ProjectFile,
    ProjectPage,
    RegistryClient,
    RegistryError,
    ResolvedPyPISource,
    resolve_pypi_source,
)
from gatecheck.registry.registry_client import MalformedIndexResponse, PackageNotFound
from gatecheck.sources import PyPISource

DEFAULT_INDEX = "https://pypi.org/simple"


# ---------------------------------------------------------------------------
# Hermetic seam — an in-memory RegistryClient (§5 / §10). Never touches network.
# ---------------------------------------------------------------------------


class FakeRegistryClient:
    """In-memory ``RegistryClient`` returning canned pages and recording calls.

    Keyed by the *canonical* project name the resolver passes to ``fetch_project``.
    When constructed with ``error=...`` every call raises that signal (to drive the
    error matrix offline). ``calls`` records every ``fetch_project`` invocation so a
    test can assert AC-13 — the resolver only queries the index; there is no
    download / install surface to call.
    """

    def __init__(
        self,
        pages: dict[str, ProjectPage] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self._pages = dict(pages or {})
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def fetch_project(self, index_url: str, name: str) -> ProjectPage:
        self.calls.append((index_url, name))
        if self._error is not None:
            raise self._error
        try:
            return self._pages[name]
        except KeyError as exc:  # pragma: no cover - defensive; tests inject pages
            raise PackageNotFound(name) from exc


def _wheel(
    dist: str,
    version: str,
    *,
    yanked: bool = False,
    sha256: str | None = None,
    url: str | None = None,
) -> ProjectFile:
    return ProjectFile(
        filename=f"{dist}-{version}-py3-none-any.whl",
        url=url,
        sha256=sha256,
        yanked=yanked,
    )


def _sdist(
    dist: str,
    version: str,
    *,
    yanked: bool = False,
    sha256: str | None = None,
    url: str | None = None,
) -> ProjectFile:
    return ProjectFile(
        filename=f"{dist}-{version}.tar.gz",
        url=url,
        sha256=sha256,
        yanked=yanked,
    )


def _page(
    name: str,
    versions: list[str],
    *,
    dist: str | None = None,
    yanked_versions: tuple[str, ...] = (),
) -> ProjectPage:
    dist = dist or name
    files = tuple(_wheel(dist, v, yanked=(v in yanked_versions)) for v in versions)
    return ProjectPage(name=name, files=files)


def _client(name: str, versions: list[str], **kwargs: object) -> FakeRegistryClient:
    return FakeRegistryClient({name: _page(name, versions, **kwargs)})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# AC-1 — exact pin returns the full pinned descriptor
# ---------------------------------------------------------------------------


def test_exact_pin_returns_full_descriptor() -> None:
    # Arrange
    client = _client("ruff", ["0.4.1", "0.4.9", "1.0.0"])
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert — the load-bearing fields (AC-1); filename is best-effort (AC-12).
    assert isinstance(result, ResolvedPyPISource)
    assert result.kind == "pypi"
    assert result.requirement == "ruff==0.4.9"
    assert result.name == "ruff"
    assert result.version == "0.4.9"
    assert result.index_url == DEFAULT_INDEX
    assert result.registry is None
    # This fixture's wheel carries no url/hash, so those stay None; filename is set.
    assert result.sha256 is None
    assert result.url is None
    assert result.filename == "ruff-0.4.9-py3-none-any.whl"


# ---------------------------------------------------------------------------
# BUG-0001 — every artifact hash for the selected version must be carried
# ---------------------------------------------------------------------------


def test_all_hashes_for_the_selected_version_are_collected() -> None:
    # Arrange — one version, several platform wheels plus an sdist (the ruff shape)
    page = ProjectPage(
        name="ruff",
        files=(
            _wheel("ruff", "0.4.0", sha256="linux64"),
            _wheel("ruff", "0.4.0", sha256="macosarm"),
            _wheel("ruff", "0.4.0", sha256="win64"),
            _sdist("ruff", "0.4.0", sha256="sdisthash"),
        ),
    )
    client = FakeRegistryClient({"ruff": page})
    source = PyPISource(requirement="ruff==0.4.0", registry=None)
    # Act
    result = resolve_pypi_source(source, None, client=client)
    # Assert — all four, in index order; the representative stays the preferred wheel
    assert result.hashes == ("linux64", "macosarm", "win64", "sdisthash")
    assert result.sha256 == "linux64"


def test_files_without_a_hash_are_omitted() -> None:
    # Arrange — the index does not publish a hash for one artifact
    page = ProjectPage(
        name="ruff",
        files=(
            _wheel("ruff", "0.4.0", sha256=None),
            _wheel("ruff", "0.4.0", sha256="known"),
        ),
    )
    client = FakeRegistryClient({"ruff": page})
    source = PyPISource(requirement="ruff==0.4.0", registry=None)
    # Act
    result = resolve_pypi_source(source, None, client=client)
    # Assert — only the known hash is pinned
    assert result.hashes == ("known",)


def test_hashes_cover_only_the_selected_version() -> None:
    # Arrange — two versions; the range selects 0.4.0
    page = ProjectPage(
        name="ruff",
        files=(
            _wheel("ruff", "0.4.0", sha256="v040"),
            _wheel("ruff", "1.0.0", sha256="v100"),
        ),
    )
    client = FakeRegistryClient({"ruff": page})
    source = PyPISource(requirement="ruff==0.4.0", registry=None)
    # Act
    result = resolve_pypi_source(source, None, client=client)
    # Assert — the other version's artifact is not pinned
    assert result.hashes == ("v040",)


def test_offline_pin_carries_no_hashes() -> None:
    # Arrange — offline cannot know the artifact set
    source = PyPISource(requirement="ruff==0.4.9", registry=None)
    # Act
    result = resolve_pypi_source(source, None, offline=True)
    # Assert — empty, so the installer falls back to a plain pinned install
    assert result.hashes == ()


# ---------------------------------------------------------------------------
# Offline mode (STY-0034) — no index fetch; exact pins only
# ---------------------------------------------------------------------------


def test_offline_exact_pin_resolves_without_client() -> None:
    # Arrange — a client that would explode if consulted
    client = FakeRegistryClient(error=AssertionError("offline must not fetch"))
    source = PyPISource(requirement="ruff==0.4.9", registry=None)
    # Act
    result = resolve_pypi_source(source, None, client=client, offline=True)
    # Assert — pinned locally; no fetch happened; file metadata is unavailable
    assert result.name == "ruff"
    assert result.version == "0.4.9"
    assert result.index_url == DEFAULT_INDEX
    assert result.sha256 is None and result.url is None and result.filename is None
    assert client.calls == []


def test_offline_pin_matches_the_online_version_string() -> None:
    # Arrange — the same exact pin, resolved online vs offline
    source = PyPISource(requirement="ruff==0.4.9", registry=None)
    online = resolve_pypi_source(source, None, client=_client("ruff", ["0.4.9"]))
    # Act
    offline = resolve_pypi_source(source, None, offline=True)
    # Assert — identical version string → identical cache key material
    assert offline.version == online.version == "0.4.9"


@pytest.mark.parametrize(
    "requirement",
    ["ruff", "ruff>=0.4", "ruff~=0.4.1", "ruff>0.4.1", "ruff==0.4.*", "ruff==0.4,!=0.4.1"],
)
def test_offline_non_exact_pin_errors(requirement: str) -> None:
    # Arrange
    source = PyPISource(requirement=requirement, registry=None)
    # Act / Assert — a clear, actionable error, no fetch
    with pytest.raises(RegistryError, match="offline mode requires an exact pin"):
        resolve_pypi_source(source, None, offline=True)


# ---------------------------------------------------------------------------
# AC-2 / AC-3 — version selection (highest satisfying; bare -> latest; ~=; >)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requirement", "versions", "expected"),
    [
        ("ruff==0.4.9", ["0.4.1", "0.4.9", "1.0.0"], "0.4.9"),  # exact pin
        ("ruff>=0.4,<1", ["0.4.1", "0.4.9", "1.0.0"], "0.4.9"),  # range -> highest
        ("ruff", ["0.4.1", "0.4.9", "1.0.0"], "1.0.0"),  # bare name -> latest
        ("ruff~=0.4.1", ["0.4.1", "0.4.9", "0.5.0", "1.0.0"], "0.4.9"),  # compatible release
        ("ruff>0.4.1", ["0.4.1", "0.4.9"], "0.4.9"),  # strict greater-than
    ],
)
def test_selects_highest_version_satisfying_specifier(
    requirement: str, versions: list[str], expected: str
) -> None:
    # Arrange
    client = _client("ruff", versions)
    source = PyPISource(requirement=requirement, registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert
    assert result.version == expected
    assert result.name == "ruff"
    assert result.kind == "pypi"
    assert result.index_url == DEFAULT_INDEX
    assert result.registry is None
    assert result.requirement == requirement


# ---------------------------------------------------------------------------
# AC-9 — pre-release rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("requirement", "versions", "allow_prereleases", "expected"),
    [
        # (a) excluded by default
        ("ruff", ["0.4.9", "0.5.0rc1"], False, "0.4.9"),
        # (b) specifier opts in via a pre-release bound
        ("ruff>=0.5.0rc1", ["0.4.9", "0.5.0rc1"], False, "0.5.0rc1"),
        # (c) specifier opts in via an exact pre-release pin
        ("ruff==0.5.0rc1", ["0.4.9", "0.5.0rc1"], False, "0.5.0rc1"),
        # (d) caller flag opts in
        ("ruff", ["0.4.9", "0.5.0rc1"], True, "0.5.0rc1"),
        # (e) only pre-releases satisfy -> selected
        ("ruff", ["0.5.0rc1", "0.5.0rc2"], False, "0.5.0rc2"),
    ],
)
def test_prerelease_selection_rules(
    requirement: str, versions: list[str], allow_prereleases: bool, expected: str
) -> None:
    # Arrange
    client = _client("ruff", versions)
    source = PyPISource(requirement=requirement, registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client, allow_prereleases=allow_prereleases)

    # Assert
    assert result.version == expected


# ---------------------------------------------------------------------------
# AC-10 — yanked rules (PEP 592)
# ---------------------------------------------------------------------------


def test_yanked_excluded_from_range_match() -> None:
    # Arrange — the highest version (0.4.9) is yanked; a range must fall back.
    client = _client("ruff", ["0.4.1", "0.4.9"], yanked_versions=("0.4.9",))
    source = PyPISource(requirement="ruff>=0.4", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert
    assert result.version == "0.4.1"


def test_yanked_selectable_when_pinned_exactly_and_only_match() -> None:
    # Arrange — the only candidate is yanked, but it is pinned exactly.
    client = _client("ruff", ["0.4.9"], yanked_versions=("0.4.9",))
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert
    assert result.version == "0.4.9"


# ---------------------------------------------------------------------------
# AC-12 — best-effort artifact fields (wheel preferred; None when unavailable)
# ---------------------------------------------------------------------------


def test_optional_fields_prefer_wheel_over_sdist() -> None:
    # Arrange — the selected version has both an sdist and a wheel.
    page = ProjectPage(
        name="ruff",
        files=(
            _sdist("ruff", "0.4.9", sha256="sdisthash", url="https://f.example/ruff-0.4.9.tar.gz"),
            _wheel(
                "ruff",
                "0.4.9",
                sha256="wheelhash",
                url="https://f.example/ruff-0.4.9-py3-none-any.whl",
            ),
        ),
    )
    client = FakeRegistryClient({"ruff": page})
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert — wheel wins.
    assert result.sha256 == "wheelhash"
    assert result.url == "https://f.example/ruff-0.4.9-py3-none-any.whl"
    assert result.filename == "ruff-0.4.9-py3-none-any.whl"


def test_optional_fields_none_when_file_entry_lacks_metadata() -> None:
    # Arrange — the file parses to a version but carries no url / hash.
    page = ProjectPage(
        name="ruff",
        files=(ProjectFile(filename="ruff-0.4.9-py3-none-any.whl", url=None, sha256=None),),
    )
    client = FakeRegistryClient({"ruff": page})
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert — resolution still succeeds on name + version + index_url.
    assert result.version == "0.4.9"
    assert result.sha256 is None
    assert result.url is None
    assert result.filename == "ruff-0.4.9-py3-none-any.whl"


# ---------------------------------------------------------------------------
# name canonicalization + fetch uses the canonical name
# ---------------------------------------------------------------------------


def test_name_is_canonicalized_and_fetch_uses_canonical_name() -> None:
    # Arrange — a non-canonical requirement name.
    client = FakeRegistryClient({"my-linter": _page("my-linter", ["1.0.0"], dist="my_linter")})
    source = PyPISource(requirement="My_Linter==1.0.0", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert
    assert result.name == "my-linter"
    assert result.version == "1.0.0"
    assert client.calls == [(DEFAULT_INDEX, "my-linter")]


# ---------------------------------------------------------------------------
# AC-4 / AC-5 — index resolution (default_registry; extra_registries alias)
# ---------------------------------------------------------------------------


def test_none_registry_and_none_sources_uses_builtin_default() -> None:
    # Arrange
    client = _client("ruff", ["0.4.9"])
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert
    assert result.index_url == DEFAULT_INDEX
    assert client.calls == [(DEFAULT_INDEX, "ruff")]


def test_default_registry_from_sources_used_as_index() -> None:
    # Arrange
    client = _client("ruff", ["0.4.9"])
    sources = SourceSpec(default_registry="https://custom.example.com/simple")
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, sources, client=client)

    # Assert
    assert result.index_url == "https://custom.example.com/simple"
    assert client.calls == [("https://custom.example.com/simple", "ruff")]


def test_alias_registry_resolves_to_extra_registries_url() -> None:
    # Arrange
    client = _client("ruff", ["0.4.9"])
    sources = SourceSpec(**{"extra-registries": {"internal": "https://pkg.example.com/simple"}})
    source = PyPISource(requirement="ruff==0.4.9", registry="internal")

    # Act
    result = resolve_pypi_source(source, sources, client=client)

    # Assert
    assert result.index_url == "https://pkg.example.com/simple"
    assert result.registry == "internal"
    assert client.calls == [("https://pkg.example.com/simple", "ruff")]


def test_index_url_trailing_slash_is_normalized_in_descriptor() -> None:
    # §4 step 1: one trailing slash is stripped from the resolved index URL.
    # Arrange
    client = _client("ruff", ["0.4.9"])
    sources = SourceSpec(default_registry="https://pypi.org/simple/")
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, sources, client=client)

    # Assert
    assert result.index_url == DEFAULT_INDEX


# ---------------------------------------------------------------------------
# Scheme guard — a non-http(s) resolved index URL is rejected before any fetch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bad_url", "scheme"),
    [
        ("file:///etc", "file"),
        ("ftp://mirror.example.com/simple", "ftp"),
    ],
)
def test_non_http_index_scheme_rejected_before_network(bad_url: str, scheme: str) -> None:
    # Arrange — the fake raises if fetched, proving the guard fires first.
    client = FakeRegistryClient({}, error=AssertionError("network must not be reached"))
    sources = SourceSpec(**{"extra-registries": {"evil": bad_url}})
    source = PyPISource(requirement="ruff", registry="evil")

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, sources, client=client)

    # Assert — exact LOCKED reason + full message; network never reached.
    err = exc_info.value
    assert err.reason == f"unsupported index URL scheme '{scheme}' (only http/https allowed)"
    assert err.index_url == bad_url
    assert str(err) == f"cannot resolve 'ruff' against {bad_url}: {err.reason}"
    assert client.calls == []


# ---------------------------------------------------------------------------
# AC-13 — resolution only queries the index (no download / install surface)
# ---------------------------------------------------------------------------


def test_resolution_only_queries_index_no_download_or_install() -> None:
    # Arrange
    client = _client("ruff", ["0.4.9"])
    source = PyPISource(requirement="ruff==0.4.9", registry=None)

    # Act
    result = resolve_pypi_source(source, None, client=client)

    # Assert — a descriptor is returned and only fetch_project was called.
    assert isinstance(result, ResolvedPyPISource)
    assert client.calls == [(DEFAULT_INDEX, "ruff")]


# ---------------------------------------------------------------------------
# AC-15 — determinism
# ---------------------------------------------------------------------------


def test_resolution_is_deterministic() -> None:
    # Arrange
    source = PyPISource(requirement="ruff>=0.4,<1", registry=None)

    # Act — two independent calls over an equal fixed index response.
    first = resolve_pypi_source(source, None, client=_client("ruff", ["0.4.1", "0.4.9", "1.0.0"]))
    second = resolve_pypi_source(source, None, client=_client("ruff", ["0.4.1", "0.4.9", "1.0.0"]))

    # Assert — frozen pydantic models compare by value.
    assert first == second


# ---------------------------------------------------------------------------
# AC-6 — unknown registry alias -> RegistryError(index_url=None)
# ---------------------------------------------------------------------------


def test_unknown_alias_raises_registry_error_with_none_index() -> None:
    # Arrange — the alias is not declared in extra_registries.
    client = _client("ruff", ["0.4.9"])
    sources = SourceSpec()
    source = PyPISource(requirement="ruff", registry="internal")

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, sources, client=client)

    # Assert — index_url is None; reason names the alias + [sources].extra-registries.
    err = exc_info.value
    assert err.index_url is None
    assert "internal" in err.reason
    assert "[sources].extra-registries" in err.reason
    assert str(err) == f"cannot resolve 'ruff' against <unresolved index>: {err.reason}"
    # The index was never queried — resolution failed before the fetch.
    assert client.calls == []


# ---------------------------------------------------------------------------
# invalid requirement / markers / extras
# ---------------------------------------------------------------------------


def test_invalid_requirement_raises_registry_error() -> None:
    # Arrange
    client = FakeRegistryClient({})
    source = PyPISource(requirement="!!!bad", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert
    err = exc_info.value
    assert err.index_url == DEFAULT_INDEX
    assert "invalid requirement" in err.reason
    assert client.calls == []


@pytest.mark.parametrize(
    "requirement",
    [
        "ruff[dev]",  # extras
        "ruff; python_version >= '3.10'",  # marker
    ],
)
def test_markers_or_extras_are_rejected(requirement: str) -> None:
    # Arrange
    client = FakeRegistryClient({})
    source = PyPISource(requirement=requirement, registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert — LOCKED reject-not-ignore reason.
    err = exc_info.value
    assert err.reason == "requirement markers/extras are not supported"
    assert client.calls == []


# ---------------------------------------------------------------------------
# AC-7 — package not found
# ---------------------------------------------------------------------------


def test_package_not_found_raises_registry_error() -> None:
    # Arrange — the client raises PackageNotFound (index 404 for the project).
    client = FakeRegistryClient({}, error=PackageNotFound("ruff"))
    source = PyPISource(requirement="ruff", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert
    err = exc_info.value
    assert err.index_url == DEFAULT_INDEX
    assert "not found" in err.reason
    assert "ruff" in err.reason


# ---------------------------------------------------------------------------
# AC-8 — no version satisfies the specifier
# ---------------------------------------------------------------------------


def test_no_version_satisfies_raises_registry_error() -> None:
    # Arrange
    client = _client("ruff", ["0.4.1"])
    source = PyPISource(requirement="ruff>=99", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert — exact LOCKED reason + full message form.
    err = exc_info.value
    assert err.index_url == DEFAULT_INDEX
    assert err.reason == "no version of 'ruff' satisfies '>=99'"
    assert str(err) == (
        "cannot resolve 'ruff>=99' against https://pypi.org/simple: "
        "no version of 'ruff' satisfies '>=99'"
    )


# ---------------------------------------------------------------------------
# AC-11 — malformed index response + network error wrapped via raise ... from
# ---------------------------------------------------------------------------


def test_malformed_index_response_raises_registry_error() -> None:
    # Arrange — the client raises MalformedIndexResponse (unparseable body).
    client = FakeRegistryClient({}, error=MalformedIndexResponse("bad json"))
    source = PyPISource(requirement="ruff", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert
    err = exc_info.value
    assert err.index_url == DEFAULT_INDEX
    assert "malformed index response" in err.reason


@pytest.mark.parametrize(
    "network_error",
    [
        URLError("connection refused"),
        TimeoutError("read timed out"),
        OSError("connection reset by peer"),
    ],
)
def test_network_error_is_wrapped_via_raise_from(network_error: Exception) -> None:
    # Arrange — the client lets a raw network error propagate.
    client = FakeRegistryClient({}, error=network_error)
    source = PyPISource(requirement="ruff", registry=None)

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_pypi_source(source, None, client=client)

    # Assert — wrapped (never the raw urllib/OS error) and chained via `from`.
    err = exc_info.value
    assert err.index_url == DEFAULT_INDEX
    assert "network error querying index" in err.reason
    assert err.__cause__ is network_error


# ---------------------------------------------------------------------------
# AC-16 — RegistryError type + message form
# ---------------------------------------------------------------------------


def test_registry_error_is_value_error_subclass() -> None:
    # Arrange / Act / Assert
    assert issubclass(RegistryError, ValueError)


@pytest.mark.parametrize(
    ("requirement", "index_url", "reason", "expected"),
    [
        (
            "ruff",
            "https://pypi.org/simple",
            "boom",
            "cannot resolve 'ruff' against https://pypi.org/simple: boom",
        ),
        (
            "ruff",
            None,
            "unknown registry alias 'x'",
            "cannot resolve 'ruff' against <unresolved index>: unknown registry alias 'x'",
        ),
    ],
)
def test_registry_error_message_form(
    requirement: str, index_url: str | None, reason: str, expected: str
) -> None:
    # Arrange / Act
    err = RegistryError(requirement, index_url, reason)

    # Assert
    assert str(err) == expected
    assert err.requirement == requirement
    assert err.index_url == index_url
    assert err.reason == reason


# ---------------------------------------------------------------------------
# ResolvedPyPISource is a frozen value object (§3)
# ---------------------------------------------------------------------------


def test_resolved_pypi_source_is_frozen() -> None:
    # Arrange
    result = resolve_pypi_source(
        PyPISource(requirement="ruff==0.4.9", registry=None),
        None,
        client=_client("ruff", ["0.4.9"]),
    )

    # Act / Assert — frozen-instance mutation is rejected.
    with pytest.raises(pydantic.ValidationError):
        result.version = "9.9.9"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AC-21 — resolve_source (STY-0005) is unchanged; still rejects PyPISource
# ---------------------------------------------------------------------------


def test_resolve_source_still_rejects_pypi_unchanged() -> None:
    # Arrange
    from gatecheck.sources import SourceResolutionError, resolve_source

    # Act / Assert — the local resolver still delegates pypi to Environments.
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(PyPISource(requirement="ruff", registry=None), "ruff")
    assert exc_info.value.kind == "pypi"


# ---------------------------------------------------------------------------
# AC-18 — public import surface / facade
# ---------------------------------------------------------------------------


def test_fake_client_satisfies_registry_client_seam() -> None:
    # The injected fake is a structural RegistryClient (the whole hermetic seam).
    # Arrange / Act
    client: RegistryClient = FakeRegistryClient({"ruff": _page("ruff", ["0.4.9"])})
    result = resolve_pypi_source(
        PyPISource(requirement="ruff==0.4.9", registry=None), None, client=client
    )

    # Assert
    assert result.version == "0.4.9"


def test_public_import_surface() -> None:
    # AC-18: the locked facade symbols import from gatecheck.registry.
    # Arrange / Act
    import gatecheck.registry as registry
    from gatecheck.registry import (
        ProjectFile as _ProjectFile,
    )
    from gatecheck.registry import (
        ProjectPage as _ProjectPage,
    )
    from gatecheck.registry import (
        RegistryClient as _RegistryClient,
    )
    from gatecheck.registry import (
        RegistryError as _RegistryError,
    )
    from gatecheck.registry import (
        ResolvedPyPISource as _ResolvedPyPISource,
    )
    from gatecheck.registry import (
        UrllibRegistryClient as _UrllibRegistryClient,
    )
    from gatecheck.registry import (
        resolve_pypi_source as _resolve_pypi_source,
    )

    # Assert
    assert callable(_resolve_pypi_source)
    assert issubclass(_RegistryError, ValueError)
    assert isinstance(_ResolvedPyPISource, type)
    assert isinstance(_ProjectFile, type)
    assert isinstance(_ProjectPage, type)
    assert isinstance(_UrllibRegistryClient, type)
    assert _RegistryClient is not None
    assert set(registry.__all__) == {
        "ProjectFile",
        "ProjectPage",
        "RegistryClient",
        "RegistryError",
        "ResolvedPyPISource",
        "UrllibRegistryClient",
        "resolve_pypi_source",
    }
