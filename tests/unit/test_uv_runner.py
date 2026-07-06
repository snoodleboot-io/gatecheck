"""Unit tests for gatecheck.env.uv_runner (STY-0008 / GAT-10).

Hermetic — no real ``uv`` and no real ``subprocess``: ``_run`` is patched to record
argv, and ``subprocess.run`` is patched at the module boundary for the exit-code
paths. Covers uv discovery (``GATECHECK_UV`` override + PATH), the ``uv venv`` /
``uv pip install`` argv for the hash and no-hash branches, and the ``UvNotFound`` /
``UvBuildError`` signals. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gatecheck.env import uv_runner as uv_runner_module
from gatecheck.env.uv_runner import (
    SubprocessUvRunner,
    UvBuildError,
    UvNotFound,
)
from gatecheck.registry import ResolvedPyPISource

INDEX = "https://pypi.org/simple"


def _pinned(sha256: str | None = None) -> ResolvedPyPISource:
    return ResolvedPyPISource(
        kind="pypi",
        requirement="ruff==0.4.0",
        name="ruff",
        version="0.4.0",
        index_url=INDEX,
        sha256=sha256,
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
        "/v/bin/python",
        "ruff==0.4.0",
        "--index-url",
        INDEX,
    ]


def test_install_argv_with_hash_uses_require_hashes_and_reqfile() -> None:
    # Act
    argv = SubprocessUvRunner._install_argv(
        "uv", _pinned("deadbeef"), Path("/v/bin/python"), "/tmp/r.txt"
    )
    # Assert
    assert "--require-hashes" in argv
    assert argv[argv.index("-r") + 1] == "/tmp/r.txt"
    assert "ruff==0.4.0" not in argv  # requirement travels via the file, not argv


# ── build_venv argv (via a recording _run) ────────────────────────


def test_build_venv_runs_uv_venv_then_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    dest = tmp_path / "venv"
    runner = SubprocessUvRunner({"GATECHECK_UV": _fake_uv(tmp_path)})
    recorded: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda argv: recorded.append(argv))
    # Act
    runner.build_venv(_pinned(), dest)
    # Assert — venv creation first, then install targeting the venv python
    assert recorded[0] == [runner._find_uv(), "venv", str(dest)]
    assert recorded[1][:5] == [
        runner._find_uv(),
        "pip",
        "install",
        "--python",
        str(dest / "bin" / "python"),
    ]


def test_build_venv_passes_require_hashes_when_sha_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange
    runner = SubprocessUvRunner({"GATECHECK_UV": _fake_uv(tmp_path)})
    recorded: list[list[str]] = []
    monkeypatch.setattr(runner, "_run", lambda argv: recorded.append(argv))
    # Act
    runner.build_venv(_pinned("cafef00d"), tmp_path / "venv")
    # Assert
    assert "--require-hashes" in recorded[1]


# ── _find_uv ──────────────────────────────────────────────────────


def test_find_uv_override_must_be_executable(tmp_path: Path) -> None:
    # Arrange — a non-executable override target
    plain = tmp_path / "not-uv"
    plain.write_text("", encoding="utf-8")
    runner = SubprocessUvRunner({"GATECHECK_UV": str(plain)})
    # Act / Assert
    with pytest.raises(UvNotFound, match="GATECHECK_UV"):
        runner._find_uv()


def test_find_uv_absent_on_path_raises(tmp_path: Path) -> None:
    # Arrange — an empty PATH dir with no uv, no override
    runner = SubprocessUvRunner({"PATH": str(tmp_path)})
    # Act / Assert
    with pytest.raises(UvNotFound, match="STY-0010"):
        runner._find_uv()


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
