"""Unit tests for EnvManager.explain — read-only cache explainability (STY-0009 / GAT-11).

Hermetic: system/project resolve against ``tmp_path`` fakes (injected ``environ`` /
``workspace_root``); the pypi path uses a dependency-injected ``FakeRegistryClient``
(no network) and inspects — never builds — a ``tmp_path`` cache root. Asserts the
status matrix (not-applicable / hit / miss), that ``key_material`` reproduces the
``cache_key`` digest, and that ``explain`` creates no directory and spawns no
subprocess. AAA structure throughout.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.env import CacheExplanation, EnvManager
from gatecheck.env.env_cache import venv_slot
from gatecheck.registry import ProjectFile, ProjectPage
from gatecheck.venv import bin_dir_name

DEFAULT_INDEX = "https://pypi.org/simple"


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """explain() is read-only — it must never spawn a subprocess."""

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("EnvManager.explain must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


class FakeRegistryClient:
    """In-memory RegistryClient returning a canned page (no network)."""

    def __init__(self, page: ProjectPage) -> None:
        self._page = page

    def fetch_project(self, index_url: str, name: str) -> ProjectPage:
        return self._page


def _ruff_page() -> ProjectPage:
    return ProjectPage(
        name="ruff",
        files=(ProjectFile(filename="ruff-0.4.0-py3-none-any.whl", url="https://x/ruff.whl"),),
    )


def _hook(from_spec: str, run: str = "ruff check", hook_id: str = "lint") -> HookDef:
    return HookDef.model_validate({"id": hook_id, "from": from_spec, "run": run})


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".bat")
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return path


def _digest(*material: str) -> str:
    return hashlib.sha256("\n".join(material).encode("utf-8")).hexdigest()


# ── non-venv: not-applicable ──────────────────────────────────────


def test_explain_system_is_not_applicable_with_reproducible_key(tmp_path: Path) -> None:
    # Arrange
    exe = _make_executable(tmp_path / bin_dir_name() / "ruff")
    manager = EnvManager(environ={"PATH": str(tmp_path / bin_dir_name())})
    # Act
    ex = manager.explain(_hook("system"))
    # Assert
    assert isinstance(ex, CacheExplanation)
    assert ex.source_kind == "system"
    assert ex.status == "not-applicable"
    assert ex.cache_key == _digest("env-v1", "system", str(exe.resolve()))
    # key_material reproduces the digest by hand
    assert _digest(*ex.key_material) == ex.cache_key


def test_explain_project_reports_venv_bin_dir(tmp_path: Path) -> None:
    # Arrange
    exe = _make_executable(tmp_path / ".venv" / bin_dir_name() / "ruff")
    manager = EnvManager(workspace_root=tmp_path, environ={"PATH": "/nonexistent"})
    # Act
    ex = manager.explain(_hook("project"))
    # Assert
    assert ex.source_kind == "project"
    assert ex.status == "not-applicable"
    assert ex.cache_dir == str(exe.resolve().parent)


# ── pypi: hit / miss ──────────────────────────────────────────────


def test_explain_pypi_miss_when_no_slot(tmp_path: Path) -> None:
    # Arrange — cache root empty
    manager = EnvManager(cache_root=tmp_path, client=FakeRegistryClient(_ruff_page()))
    # Act
    ex = manager.explain(_hook("pypi:ruff==0.4.0"))
    # Assert
    assert ex.source_kind == "pypi"
    assert ex.status == "miss"
    assert ex.cache_key == _digest("env-v1", "pypi", "ruff", "0.4.0", DEFAULT_INDEX)
    # explain must NOT have created the slot
    assert not Path(ex.cache_dir).exists()


def test_explain_pypi_hit_when_slot_present(tmp_path: Path) -> None:
    # Arrange — pre-create a healthy venv slot for the pinned key
    manager = EnvManager(cache_root=tmp_path, client=FakeRegistryClient(_ruff_page()))
    key = _digest("env-v1", "pypi", "ruff", "0.4.0", DEFAULT_INDEX)
    (venv_slot(tmp_path, key) / bin_dir_name()).mkdir(parents=True)
    # Act
    ex = manager.explain(_hook("pypi:ruff==0.4.0"))
    # Assert
    assert ex.status == "hit"
    assert ex.cache_key == key


def test_explain_pypi_to_dict_round_trips(tmp_path: Path) -> None:
    # Arrange
    manager = EnvManager(cache_root=tmp_path, client=FakeRegistryClient(_ruff_page()))
    # Act
    payload = manager.explain(_hook("pypi:ruff==0.4.0")).to_dict()
    # Assert — JSON-shaped dict carries the same fields
    assert payload["status"] == "miss"
    assert payload["cache_key"] == _digest("env-v1", "pypi", "ruff", "0.4.0", DEFAULT_INDEX)
    assert payload["key_material"] == ["env-v1", "pypi", "ruff", "0.4.0", DEFAULT_INDEX]
