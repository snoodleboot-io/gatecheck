"""Unit tests for EnvManager's pypi branch — uv-backed venv build + cache (STY-0008 / GAT-10).

Hermetic: the network is a dependency-injected ``FakeRegistryClient`` (canned
``ProjectPage``) and ``uv`` is a ``FakeUvRunner`` that materializes a venv directory
without a subprocess; the cache root is a ``tmp_path``. Covers build-then-cache-hit
(build once), the content-addressed ``cache_key``, ``pypi+alias`` index forwarding,
``RegistryError`` propagation (unwrapped), and the ``EnvError`` mapping for
uv-absent / uv-build-failure / tool-missing. AAA structure throughout.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from gatecheck.config import SourceSpec
from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvError, EnvManager, ResolvedEnv
from gatecheck.env.uv_bootstrap import UvBootstrapError
from gatecheck.env.uv_runner import UvBuildError, UvNotFound
from gatecheck.registry import ProjectFile, ProjectPage, RegistryError, ResolvedPyPISource
from gatecheck.venv import bin_dir_name

_OFFLINE = {"GATECHECK_OFFLINE": "1"}

DEFAULT_INDEX = "https://pypi.org/simple"


# ── hermetic seams ────────────────────────────────────────────────


class FakeRegistryClient:
    """In-memory RegistryClient returning a canned page and recording index calls."""

    def __init__(self, page: ProjectPage, *, error: Exception | None = None) -> None:
        self._page = page
        self._error = error
        self.calls: list[tuple[str, str]] = []

    def fetch_project(self, index_url: str, name: str) -> ProjectPage:
        self.calls.append((index_url, name))
        if self._error is not None:
            raise self._error
        return self._page


class FakeUvRunner:
    """UvRunner that fabricates a venv dir (bin/python + one script per tool)."""

    def __init__(self, tools: tuple[str, ...] = ("ruff",)) -> None:
        self._tools = tools
        self.calls: list[tuple[ResolvedPyPISource, Path]] = []

    def build_venv(self, pinned: ResolvedPyPISource, dest: Path) -> None:
        self.calls.append((pinned, dest))
        bin_dir = dest / bin_dir_name()
        bin_dir.mkdir(parents=True)
        (bin_dir / "python").write_text("", encoding="utf-8")
        for tool in self._tools:
            (bin_dir / tool).write_text("", encoding="utf-8")


class RaisingUvRunner:
    """UvRunner that always raises a chosen uv signal, to drive the error mapping."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def build_venv(self, pinned: ResolvedPyPISource, dest: Path) -> None:
        raise self._error


def _ruff_page() -> ProjectPage:
    return ProjectPage(
        name="ruff",
        files=(ProjectFile(filename="ruff-0.4.0-py3-none-any.whl", url="https://x/ruff.whl"),),
    )


def _hook(from_spec: str, run: str = "ruff check", hook_id: str = "lint") -> HookDef:
    return HookDef.model_validate({"id": hook_id, "from": from_spec, "run": run})


def _expected_pypi_key(index_url: str = DEFAULT_INDEX) -> str:
    material = "\n".join(["env-v1", "pypi", "ruff", "0.4.0", index_url])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ── build + cache ─────────────────────────────────────────────────


def test_pypi_builds_venv_and_returns_resolved_env(tmp_path: Path) -> None:
    # Arrange
    client = FakeRegistryClient(_ruff_page())
    runner = FakeUvRunner()
    manager = EnvManager(cache_root=tmp_path, client=client, uv_runner=runner)
    # Act
    env = manager.resolve(_hook("pypi:ruff==0.4.0"))
    # Assert
    assert isinstance(env, ResolvedEnv)
    assert env.cache_key == _expected_pypi_key()
    assert env.bin_dir == tmp_path / "env-v1" / env.cache_key / bin_dir_name()
    assert (env.bin_dir / "ruff").exists()
    assert len(runner.calls) == 1


def test_second_resolve_is_a_cache_hit(tmp_path: Path) -> None:
    # Arrange
    runner = FakeUvRunner()
    manager = EnvManager(
        cache_root=tmp_path, client=FakeRegistryClient(_ruff_page()), uv_runner=runner
    )
    # Act — resolve twice
    first = manager.resolve(_hook("pypi:ruff==0.4.0"))
    second = manager.resolve(_hook("pypi:ruff==0.4.0"))
    # Assert — identical result, built only once
    assert first == second
    assert len(runner.calls) == 1


def test_pypi_alias_forwards_the_aliased_index(tmp_path: Path) -> None:
    # Arrange
    client = FakeRegistryClient(_ruff_page())
    sources = SourceSpec.model_validate(
        {"extra-registries": {"internal": "https://internal/simple"}}
    )
    manager = EnvManager(
        cache_root=tmp_path, client=client, uv_runner=FakeUvRunner(), sources=sources
    )
    # Act
    env = manager.resolve(_hook("pypi+internal:ruff==0.4.0"))
    # Assert — the fake index was queried with the aliased URL, key reflects it
    assert client.calls == [("https://internal/simple", "ruff")]
    assert env.cache_key == _expected_pypi_key("https://internal/simple")


# ── error mapping ─────────────────────────────────────────────────


def test_registry_error_propagates_unwrapped(tmp_path: Path) -> None:
    # Arrange — a client whose fetch fails; resolve_pypi_source wraps it as RegistryError
    from gatecheck.registry.registry_client import PackageNotFound

    client = FakeRegistryClient(_ruff_page(), error=PackageNotFound("ruff"))
    manager = EnvManager(cache_root=tmp_path, client=client, uv_runner=FakeUvRunner())
    # Act / Assert — NOT wrapped in EnvError
    with pytest.raises(RegistryError):
        manager.resolve(_hook("pypi:ruff==0.4.0"))


def test_uv_not_found_maps_to_env_error(tmp_path: Path) -> None:
    # Arrange
    manager = EnvManager(
        cache_root=tmp_path,
        client=FakeRegistryClient(_ruff_page()),
        uv_runner=RaisingUvRunner(UvNotFound("no uv")),
    )
    # Act / Assert
    with pytest.raises(EnvError, match="unavailable") as exc_info:
        manager.resolve(_hook("pypi:ruff==0.4.0"))
    assert exc_info.value.hook_id == "lint"


def test_uv_bootstrap_error_maps_to_env_error(tmp_path: Path) -> None:
    # Arrange — the runner's bootstrap fails (e.g. checksum mismatch)
    manager = EnvManager(
        cache_root=tmp_path,
        client=FakeRegistryClient(_ruff_page()),
        uv_runner=RaisingUvRunner(UvBootstrapError("checksum mismatch")),
    )
    # Act / Assert
    with pytest.raises(EnvError, match="auto-bootstrap uv"):
        manager.resolve(_hook("pypi:ruff==0.4.0"))


def test_uv_build_error_maps_to_env_error(tmp_path: Path) -> None:
    # Arrange
    manager = EnvManager(
        cache_root=tmp_path,
        client=FakeRegistryClient(_ruff_page()),
        uv_runner=RaisingUvRunner(UvBuildError("exit 1")),
    )
    # Act / Assert
    with pytest.raises(EnvError, match="uv failed to build"):
        manager.resolve(_hook("pypi:ruff==0.4.0"))


def test_missing_tool_in_built_venv_maps_to_env_error(tmp_path: Path) -> None:
    # Arrange — runner builds a venv WITHOUT the 'ruff' script
    manager = EnvManager(
        cache_root=tmp_path,
        client=FakeRegistryClient(_ruff_page()),
        uv_runner=FakeUvRunner(tools=()),
    )
    # Act / Assert
    with pytest.raises(EnvError, match="tool 'ruff' is not present"):
        manager.resolve(_hook("pypi:ruff==0.4.0"))


# ── offline mode (STY-0034) ───────────────────────────────────────


def _seed_slot(cache_root: Path, key: str, tools: tuple[str, ...] = ("ruff",)) -> None:
    """Materialize a healthy venv slot at ``key`` (as a warm-cache stand-in)."""
    bin_dir = cache_root / "env-v1" / key / bin_dir_name()
    bin_dir.mkdir(parents=True)
    (bin_dir / "python").write_text("", encoding="utf-8")
    for tool in tools:
        (bin_dir / tool).write_text("", encoding="utf-8")


def test_offline_cache_hit_resolves_without_network_or_uv(tmp_path: Path) -> None:
    # Arrange — warm the cache, then resolve offline; uv/registry would raise if used
    key = _expected_pypi_key()
    _seed_slot(tmp_path, key)
    manager = EnvManager(
        environ=_OFFLINE,
        cache_root=tmp_path,
        uv_runner=RaisingUvRunner(AssertionError("uv must not run offline")),
    )
    # Act
    env = manager.resolve(_hook("pypi:ruff==0.4.0"))
    # Assert — served entirely from the warm cache
    assert env.cache_key == key
    assert (env.bin_dir / "ruff").exists()


def test_offline_cache_miss_is_a_clear_error(tmp_path: Path) -> None:
    # Arrange — empty cache, offline
    manager = EnvManager(
        environ=_OFFLINE,
        cache_root=tmp_path,
        uv_runner=RaisingUvRunner(AssertionError("uv must not run offline")),
    )
    # Act / Assert — a clear offline error naming the hook, not a build attempt
    with pytest.raises(EnvError, match="offline: no cached environment") as exc_info:
        manager.resolve(_hook("pypi:ruff==0.4.0"))
    assert exc_info.value.hook_id == "lint"


def test_offline_non_exact_pin_errors(tmp_path: Path) -> None:
    # Arrange
    manager = EnvManager(environ=_OFFLINE, cache_root=tmp_path)
    # Act / Assert — cannot resolve a range without the index
    with pytest.raises(RegistryError, match="offline mode requires an exact pin"):
        manager.resolve(_hook("pypi:ruff>=0.4"))


def test_offline_explain_reports_miss_without_network(tmp_path: Path) -> None:
    # Arrange — offline explain of an uncached exact pin
    manager = EnvManager(environ=_OFFLINE, cache_root=tmp_path)
    # Act
    explanation = manager.explain(_hook("pypi:ruff==0.4.0"))
    # Assert — a miss, derived locally
    assert explanation.status == "miss"
    assert explanation.cache_key == _expected_pypi_key()
