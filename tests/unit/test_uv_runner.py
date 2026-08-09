"""Unit tests for hooksmith.env.uv_runner (STY-0008 / GAT-10).

Hermetic — no real ``uv`` and no real ``subprocess``: ``_run`` is patched to record
argv, and ``subprocess.run`` is patched at the module boundary for the exit-code
paths. Covers uv discovery (``HOOKSMITH_UV`` override + PATH), the ``uv venv`` /
``uv pip install`` argv for the hash and no-hash branches, and the ``UvNotFound`` /
``UvBuildError`` signals. AAA structure throughout.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hooksmith import venv
from hooksmith.env import uv_runner as uv_runner_module
from hooksmith.env.uv_runner import (
    SubprocessUvRunner,
    UvBuildError,
    UvNotFound,
)
from hooksmith.registry import ResolvedPyPISource

INDEX = "https://pypi.org/simple"


def _pinned() -> ResolvedPyPISource:
    """A pinned source at an exact version."""
    return ResolvedPyPISource(
        kind="pypi",
        requirement="ruff==0.4.0",
        name="ruff",
        version="0.4.0",
        index_url=INDEX,
    )


def _fake_uv(tmp_path: Path) -> str:
    """Create an executable stand-in for the uv binary and return its path."""
    uv = tmp_path / "uv"
    uv.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    uv.chmod(0o755)
    return str(uv)


# ── _install_argv ─────────────────────────────────────────────────


def test_install_argv_no_hash() -> None:
    # Act
    argv = SubprocessUvRunner._install_argv("uv", _pinned(), Path("/v/bin/python"))
    # Assert
    assert argv == [
        "uv",
        "pip",
        "install",
        "--python",
        str(Path("/v/bin/python")),
        "ruff==0.4.0",
        "--index-url",
        INDEX,
    ]


# ── build_venv argv (via a recording _run) ────────────────────────


def test_build_venv_runs_uv_venv_then_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    dest = tmp_path / "venv"
    runner = SubprocessUvRunner({"HOOKSMITH_UV": _fake_uv(tmp_path)})
    recorded: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda argv: recorded.append(argv))
    # Act
    runner.build_venv(_pinned(), dest)
    # Assert — venv creation first (no --python by default), then install
    assert recorded[0] == [runner._find_uv(), "venv", "--relocatable", str(dest)]


def test_build_venv_passes_python_version_when_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a package pinned to 3.9
    dest = tmp_path / "venv"
    runner = SubprocessUvRunner({"HOOKSMITH_UV": _fake_uv(tmp_path)}, python_version="3.9")
    recorded: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda argv: recorded.append(argv))
    # Act
    runner.build_venv(_pinned(), dest)
    # Assert — uv is told which interpreter to build with
    assert recorded[0] == [runner._find_uv(), "venv", "--relocatable", "--python", "3.9", str(dest)]
    assert recorded[1][:5] == [
        runner._find_uv(),
        "pip",
        "install",
        "--python",
        str(venv.python_executable(dest)),
    ]


def test_install_is_a_plain_version_pin_without_require_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BUG-0006: install NAME==VERSION and let uv resolve the tree. --require-hashes
    would demand every transitive dependency be pinned+hashed too, which hooksmith
    can't provide, so it must not be used."""
    # Arrange
    runner = SubprocessUvRunner({"HOOKSMITH_UV": _fake_uv(tmp_path)})
    recorded: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda argv: recorded.append(argv))
    # Act
    runner.build_venv(_pinned(), tmp_path / "venv")
    # Assert — the install is a plain exact pin against the index, no hashes involved
    install = recorded[1]
    assert "--require-hashes" not in install
    assert "-r" not in install
    assert "ruff==0.4.0" in install
    assert install[install.index("--index-url") + 1] == INDEX


# ── _find_uv ──────────────────────────────────────────────────────


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX exec-bit; os.access(X_OK) is always True on Windows"
)
def test_find_uv_override_must_be_executable(tmp_path: Path) -> None:
    # Arrange — a non-executable override target
    plain = tmp_path / "not-uv"
    plain.write_text("", encoding="utf-8")
    runner = SubprocessUvRunner({"HOOKSMITH_UV": str(plain)})
    # Act / Assert
    with pytest.raises(UvNotFound, match="HOOKSMITH_UV"):
        runner._find_uv()


def test_find_uv_absent_raises_when_bootstrap_disabled(tmp_path: Path) -> None:
    # Arrange — no uv on PATH, bootstrap turned off
    runner = SubprocessUvRunner({"PATH": str(tmp_path)}, allow_bootstrap=False)
    # Act / Assert
    with pytest.raises(UvNotFound, match="uv not found"):
        runner._find_uv()


def test_find_uv_absent_raises_when_no_bootstrap_env_set(tmp_path: Path) -> None:
    # Arrange — HOOKSMITH_NO_BOOTSTRAP disables auto-download even with allow_bootstrap
    runner = SubprocessUvRunner({"PATH": str(tmp_path), "HOOKSMITH_NO_BOOTSTRAP": "1"})
    # Act / Assert
    with pytest.raises(UvNotFound):
        runner._find_uv()


def test_find_uv_bootstraps_when_absent(tmp_path: Path) -> None:
    # Arrange — no uv on PATH; inject a fake bootstrapper (no network)
    def fake_bootstrapper(cache_root: Path) -> Path:
        uv = cache_root / "bin" / "uv"
        uv.parent.mkdir(parents=True, exist_ok=True)
        uv.write_text("#!/bin/sh\n", encoding="utf-8")
        uv.chmod(0o755)
        return uv

    runner = SubprocessUvRunner(
        {"PATH": "/nonexistent"}, cache_root=tmp_path, bootstrapper=fake_bootstrapper
    )
    # Act
    located = runner._find_uv()
    # Assert
    assert located == str(tmp_path / "bin" / "uv")


# ── _run exit-code mapping ────────────────────────────────────────


def test_run_nonzero_exit_raises_uv_build_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    runner = SubprocessUvRunner()

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=1, stderr="explosion in uv\n")

    monkeypatch.setattr(uv_runner_module.subprocess, "run", fake_run)
    # Act / Assert
    with pytest.raises(UvBuildError, match="explosion in uv"):
        runner._run(["uv", "venv", "/x"])


def test_run_missing_binary_raises_uv_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    runner = SubprocessUvRunner()

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        raise FileNotFoundError("no uv here")

    monkeypatch.setattr(uv_runner_module.subprocess, "run", fake_run)
    # Act / Assert
    with pytest.raises(UvNotFound):
        runner._run(["uv", "venv", "/x"])
