"""Unit tests for hooksmith.venv — cross-platform venv layout (STY-0023 / GAT-25).

Hermetic — the platform is simulated by patching ``venv._is_windows`` (not
``os.name``, which would make ``pathlib`` dispatch ``WindowsPath`` and break on a
POSIX host). Covers the POSIX/Windows bin dir, python path, executable-name
candidates, the exec check, and that the resolver honors ``Scripts/`` + ``.exe`` on
Windows. AAA throughout.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from hooksmith import venv
from hooksmith.sources import parse_source, resolve_source


def _as_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(venv, "_is_windows", lambda: True)


def _as_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(venv, "_is_windows", lambda: False)


def test_posix_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    _as_posix(monkeypatch)
    # Assert
    assert venv.bin_dir_name() == "bin"
    assert venv.bin_dir(Path("/v")) == Path("/v/bin")
    assert venv.python_executable(Path("/v")) == Path("/v/bin/python")
    assert venv.executable_candidates("ruff") == ("ruff",)


def test_windows_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    _as_windows(monkeypatch)
    # Assert
    assert venv.bin_dir_name() == "Scripts"
    assert venv.bin_dir(Path("/v")) == Path("/v/Scripts")
    assert venv.python_executable(Path("/v")) == Path("/v/Scripts/python.exe")
    assert "ruff.exe" in venv.executable_candidates("ruff")


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX exec-bit; os.access(X_OK) is always True on Windows"
)
def test_is_executable_posix_needs_exec_bit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    _as_posix(monkeypatch)
    tool = tmp_path / "tool"
    tool.write_text("", encoding="utf-8")
    # Assert — no exec bit yet
    assert venv.is_executable(tool) is False
    tool.chmod(0o755)
    assert venv.is_executable(tool) is True


def test_is_executable_windows_needs_only_existence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange
    _as_windows(monkeypatch)
    tool = tmp_path / "tool.exe"
    tool.write_text("", encoding="utf-8")
    # Assert
    assert venv.is_executable(tool) is True
    assert venv.is_executable(tmp_path / "missing.exe") is False


def test_resolver_finds_tool_in_scripts_on_windows(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Arrange — simulate Windows and a project venv with Scripts/ruff.exe
    _as_windows(monkeypatch)
    exe = tmp_path / ".venv" / "Scripts" / "ruff.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("", encoding="utf-8")
    # Act
    resolved = resolve_source(
        parse_source("project"), "ruff", workspace_root=tmp_path, environ={"PATH": ""}
    )
    # Assert
    assert resolved.origin == "project"
    assert resolved.executable == exe.resolve()
