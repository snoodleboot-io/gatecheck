"""Integration tests for `hooksmith sync` (STY-0021 / GAT-20).

End-to-end via ``CliRunner`` with real ``system`` hooks: a tool on PATH resolves to
``ready``; a missing tool is an ``error`` with a non-zero exit. Marked ``integration``
and skipped when ``echo`` is absent.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from hooksmith.cli.main import main

pytestmark = pytest.mark.integration

_skip = pytest.mark.skipif(shutil.which("echo") is None, reason="echo not on PATH")


@_skip
def test_sync_system_hook_is_ready_exit_zero() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("check.toml").write_text(
            '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo hi"\n', encoding="utf-8"
        )
        # Act
        result = runner.invoke(main, ["sync"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "ready" in result.output
        assert "say" in result.output


@_skip
def test_sync_missing_tool_is_error_exit_one() -> None:
    # Arrange — a system tool that does not exist
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("check.toml").write_text(
            '[[hook]]\nid = "ghost"\nfrom = "system"\nrun = "definitely-not-a-real-tool-xyz"\n',
            encoding="utf-8",
        )
        # Act
        result = runner.invoke(main, ["sync"])
        # Assert
        assert result.exit_code == 1, result.output
        assert "ERROR" in result.output
        assert "1 error" in result.output
