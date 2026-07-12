"""Integration test for `gatecheck run --affected` (STY-0018 / GAT-24).

End-to-end in a real monorepo git repo: two packages, a change staged in one, and
only that package's hooks run. Marked ``integration`` and skipped without git/echo.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from gatecheck.cli.main import main

pytestmark = pytest.mark.integration

_TOOLS = all(shutil.which(t) is not None for t in ("git", "echo"))
_skip = pytest.mark.skipif(not _TOOLS, reason="git/echo not on PATH")


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _pkg(name: str) -> str:
    return f'[[hook]]\nid = "lint"\nfrom = "system"\nrun = "echo {name}-lint"\npass-files = false\n'


@_skip
def test_run_affected_runs_only_changed_package() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        subprocess.run(["git", "init", "-q"], check=True, capture_output=True)
        _write(Path("check.toml"), '[workspace]\npackages = ["packages/*"]\n')
        _write(Path("packages/api/check.toml"), _pkg("api"))
        _write(Path("packages/web/check.toml"), _pkg("web"))
        # stage a change in the api package only
        _write(Path("packages/api/main.py"), "x = 1\n")
        subprocess.run(["git", "add", "packages/api/main.py"], check=True, capture_output=True)

        # Act
        result = runner.invoke(main, ["run", "--affected"])

        # Assert — only api's hook ran (prefixed with the package name)
        assert result.exit_code == 0, result.output
        assert "api:lint" in result.output
        assert "web:lint" not in result.output
