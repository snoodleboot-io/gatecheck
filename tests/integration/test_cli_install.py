"""Integration tests for `gatecheck install` (STY-0022 / GAT-21).

End-to-end via ``CliRunner`` in a real git repo: installs a managed ``pre-commit``
hook, is idempotent on re-install, and refuses to clobber an unmanaged hook. Marked
``integration`` and skipped when ``git`` is absent.
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

_skip = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")

_CONFIG = """
[[hook]]
id = "lint"
from = "system"
run = "echo hi"

[group.checks]
hooks = ["lint"]
on-event = "commit"
"""


def _init_repo() -> None:
    subprocess.run(["git", "init", "-q"], check=True, capture_output=True)


@_skip
def test_install_writes_managed_pre_commit_hook() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("check.toml").write_text(_CONFIG, encoding="utf-8")
        # Act
        result = runner.invoke(main, ["install"])
        # Assert
        assert result.exit_code == 0, result.output
        hook = Path(".git/hooks/pre-commit")
        assert hook.exists() and os.access(hook, os.X_OK)
        body = hook.read_text(encoding="utf-8")
        assert "gatecheck-managed" in body
        assert "gatecheck run checks" in body
        assert "installed" in result.output


@_skip
def test_reinstall_is_idempotent() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("check.toml").write_text(_CONFIG, encoding="utf-8")
        runner.invoke(main, ["install"])
        # Act — second install
        result = runner.invoke(main, ["install"])
        # Assert
        assert result.exit_code == 0
        assert "installed" in result.output


@_skip
def test_install_skips_unmanaged_hook() -> None:
    # Arrange — a pre-existing non-gatecheck hook
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("check.toml").write_text(_CONFIG, encoding="utf-8")
        hook = Path(".git/hooks/pre-commit")
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\necho existing\n", encoding="utf-8")
        # Act
        result = runner.invoke(main, ["install"])
        # Assert — not clobbered
        assert result.exit_code == 0
        assert "skipped" in result.output
        assert hook.read_text(encoding="utf-8") == "#!/bin/sh\necho existing\n"


@_skip
def test_install_nothing_when_no_on_event() -> None:
    # Arrange — a group without on-event
    runner = CliRunner()
    with runner.isolated_filesystem():
        _init_repo()
        Path("check.toml").write_text(
            '[[hook]]\nid = "lint"\nfrom = "system"\nrun = "echo hi"\n', encoding="utf-8"
        )
        # Act
        result = runner.invoke(main, ["install"])
        # Assert
        assert result.exit_code == 0
        assert "Nothing to install" in result.output
