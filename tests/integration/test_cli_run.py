"""Integration tests for `gatecheck run` (STY-0015 / GAT-17).

End-to-end via click's ``CliRunner`` in an isolated filesystem with a real git repo
and real ``system`` hooks (``echo`` / ``false``). Marked ``integration`` and skipped
when the required tools are absent.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from gatecheck.cli.main import main

pytestmark = pytest.mark.integration

_TOOLS_PRESENT = all(shutil.which(t) is not None for t in ("git", "echo", "false"))
_skip = pytest.mark.skipif(not _TOOLS_PRESENT, reason="git/echo/false not all on PATH")


def _init_repo() -> None:
    subprocess.run(["git", "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@e.com"], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "T"], check=True, capture_output=True)


def _write(name: str, body: str) -> None:
    Path(name).write_text(body, encoding="utf-8")


@_skip
def test_run_all_hooks_pass_exits_zero() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "ok" in result.output
        assert "1 passed" in result.output


@_skip
def test_run_offline_flag_runs_system_hooks() -> None:
    # Arrange — system hooks need no network, so --offline is a no-op for them.
    runner = CliRunner()
    try:
        with runner.isolated_filesystem():
            _init_repo()
            _write(
                "check.toml",
                '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\npass-files = false\n',
            )
            # Act — the flag is accepted and the run still passes
            result = runner.invoke(main, ["run", "--offline"])
            # Assert
            assert result.exit_code == 0, result.output
            assert "1 passed" in result.output
    finally:
        # `run --offline` sets GATECHECK_OFFLINE in the process env; clear the mutation
        # so it cannot leak into later in-process tests.
        os.environ.pop("GATECHECK_OFFLINE", None)


@_skip
def test_run_failing_hook_exits_one_and_shows_output() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write(
            "check.toml",
            '[[hook]]\nid = "nope"\nfrom = "system"\nrun = "false"\npass-files = false\n',
        )
        # Act
        result = runner.invoke(main, ["run"])
        # Assert
        assert result.exit_code == 1, result.output
        assert "FAIL  nope" in result.output
        assert "1 failed" in result.output


@_skip
def test_run_unknown_group_errors() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        _write("check.toml", '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\n')
        # Act
        result = runner.invoke(main, ["run", "ghost"])
        # Assert
        assert result.exit_code != 0
        assert "unknown group 'ghost'" in result.output
