"""Acceptance tests for EnvManager.resolve (STY-0007 + STY-0008).

Hermetic end-to-end coverage built from ``HookDef`` fixtures, exercising the
non-venv path (``project`` / ``system`` -> ``ResolvedEnv``) and the pypi branch's
pre-build failure path (an unknown alias fails at pinning). A module-wide
subprocess spy asserts these resolutions spawn NOTHING: the non-venv path is pure
filesystem lookup, and the unknown-alias pypi case errors before any ``uv`` /
network work. Happy-path uv builds are covered in ``tests/unit/test_env_manager_pypi.py``
and the opt-in ``tests/integration/test_uv_venv_build.py``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from hooksmith.config.hook_def import HookDef
from hooksmith.env import EnvManager, ResolvedEnv
from hooksmith.registry import RegistryError
from hooksmith.venv import bin_dir_name


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-13: fail loudly if any test in this module spawns a subprocess."""

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("EnvManager.resolve must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".bat")
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return path


def _hook(hook_id: str, from_spec: str, run: str) -> HookDef:
    return HookDef.model_validate({"id": hook_id, "from": from_spec, "run": run})


def test_system_hook_resolves_to_env_whose_bin_dir_holds_executable(tmp_path: Path) -> None:
    # AC-1 / AC-13
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    env = manager.resolve(_hook("lint", "system", "ruff check --fix"))

    # Assert
    assert isinstance(env, ResolvedEnv)
    assert env.bin_dir == exe.resolve().parent
    assert exe.exists()


def test_project_hook_resolves_via_dot_venv(tmp_path: Path) -> None:
    # AC-2 / AC-13
    # Arrange
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")
    manager = EnvManager(workspace_root=root, environ={"PATH": "/nonexistent"})

    # Act
    env = manager.resolve(_hook("lint", "project", "ruff check"))

    # Assert
    assert env.bin_dir == exe.resolve().parent
    assert exe.exists()


def test_pypi_hook_unknown_alias_propagates_registry_error() -> None:
    # pypi is built via uv (STY-0008); an unknown alias fails at pinning with a
    # RegistryError, before any subprocess/network — so the module's no-subprocess
    # guarantee still holds. The RegistryError propagates unwrapped (not EnvError).
    # Arrange
    manager = EnvManager(environ={"PATH": "/nonexistent"})

    # Act / Assert
    with pytest.raises(RegistryError):
        manager.resolve(_hook("fmt", "pypi+internal:x==1", "ruff format"))
