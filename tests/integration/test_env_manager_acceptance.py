"""Acceptance tests for EnvManager.resolve (STY-0007 / TSK-008).

Hermetic end-to-end coverage built from ``HookDef`` fixtures, exercising the
non-venv path (``project`` / ``system`` -> ``ResolvedEnv``) and the deferred
``pypi`` branch. A module-wide subprocess spy asserts that resolving an
environment spawns NOTHING (AC-13): the whole slice is pure filesystem lookup,
no ``uv``, no network. Contract is LOCKED by
``planning/build-plans/0007-architecture-decision.md``.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvError, EnvManager, ResolvedEnv


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-13: fail loudly if any test in this module spawns a subprocess."""

    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("EnvManager.resolve must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


def _make_executable(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _hook(hook_id: str, from_spec: str, run: str) -> HookDef:
    return HookDef.model_validate({"id": hook_id, "from": from_spec, "run": run})


def test_system_hook_resolves_to_env_whose_bin_dir_holds_executable(tmp_path: Path) -> None:
    # AC-1 / AC-13
    # Arrange
    bin_dir = tmp_path / "bin"
    exe = _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    env = manager.resolve(_hook("lint", "system", "ruff check --fix"))

    # Assert
    assert isinstance(env, ResolvedEnv)
    assert env.bin_dir == exe.resolve().parent
    assert (env.bin_dir / "ruff").exists()


def test_project_hook_resolves_via_dot_venv(tmp_path: Path) -> None:
    # AC-2 / AC-13
    # Arrange
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / "bin" / "ruff")
    manager = EnvManager(workspace_root=root, environ={"PATH": "/nonexistent"})

    # Act
    env = manager.resolve(_hook("lint", "project", "ruff check"))

    # Assert
    assert env.bin_dir == exe.resolve().parent
    assert (env.bin_dir / "ruff").exists()


def test_pypi_hook_raises_env_error_mentioning_sty_0008(tmp_path: Path) -> None:
    # AC-7 / AC-13: pypi is deferred; no subprocess (guarded by the fixture).
    # Arrange
    reason = "environment creation for pypi sources is deferred to STY-0008"
    manager = EnvManager(environ={"PATH": "/nonexistent"})

    # Act / Assert
    with pytest.raises(EnvError, match=re.escape(reason)) as exc_info:
        manager.resolve(_hook("fmt", "pypi:ruff>=0.4", "ruff format"))
    assert exc_info.value.hook_id == "fmt"
