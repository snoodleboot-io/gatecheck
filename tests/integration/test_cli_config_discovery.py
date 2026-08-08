"""Integration tests for config discovery through the CLI (GAT-48).

Via click's ``CliRunner`` in an isolated filesystem: a command run from a
subdirectory finds the ``check.toml`` in a parent, a ``pyproject.toml`` is read from
its ``[tool.hooksmith]`` table, and a run with no config anywhere is a clear error
rather than a click usage message.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from hooksmith.cli.main import main

pytestmark = pytest.mark.integration

_SYSTEM_HOOK = '[[hook]]\nid = "say"\nfrom = "system"\nrun = "echo"\npass-files = false\n'


def _has_echo() -> bool:
    import shutil

    return shutil.which("echo") is not None


@pytest.mark.skipif(not _has_echo(), reason="echo not on PATH")
def test_discovers_check_toml_from_a_subdirectory() -> None:
    # Arrange — check.toml at the root, invoke `cache why` from a nested dir
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("check.toml").write_text(_SYSTEM_HOOK, encoding="utf-8")
        nested = Path("packages") / "api"
        nested.mkdir(parents=True)
        cwd = os.getcwd()
        try:
            os.chdir(nested)
            # Act
            result = runner.invoke(main, ["cache", "why", "say"])
        finally:
            os.chdir(cwd)
        # Assert — found the parent config; no "no check.toml found" error
        assert result.exit_code == 0, result.output
        assert "say" in result.output


@pytest.mark.skipif(not _has_echo(), reason="echo not on PATH")
def test_reads_pyproject_tool_hooksmith() -> None:
    # Arrange — config only in pyproject.toml
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("pyproject.toml").write_text(
            "[tool.hooksmith]\n"
            "[[tool.hooksmith.hook]]\n"
            'id = "say"\nfrom = "system"\nrun = "echo"\npass-files = false\n',
            encoding="utf-8",
        )
        # Act
        result = runner.invoke(main, ["cache", "why", "say"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "say" in result.output


def test_no_config_anywhere_is_a_clear_error() -> None:
    # Arrange — an empty isolated filesystem
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Act
        result = runner.invoke(main, ["cache", "why", "say"])
        # Assert — a clean message, not a click usage error or a traceback
        assert result.exit_code != 0
        assert "no check.toml found" in result.output
        assert "Traceback" not in result.output
