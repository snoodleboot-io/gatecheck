"""Acceptance test for changeset resolution against a real git repo (STY-0011 / GAT-13).

Creates a throwaway repository in ``tmp_path``, stages a file, and resolves the
changeset with the real ``SubprocessGitClient``. Marked ``integration`` and skipped
when ``git`` is unavailable.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.runner import SubprocessGitClient, resolve_changeset

pytestmark = pytest.mark.integration


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")
def test_resolve_changeset_sees_staged_files(tmp_path: Path) -> None:
    # Arrange — a real repo with one staged .py and one staged .txt
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "keep.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("hi\n", encoding="utf-8")
    _git(tmp_path, "add", "keep.py", "notes.txt")

    hook = HookDef.model_validate({"id": "lint", "from": "system", "run": "ruff", "files": "*.py"})

    # Act
    result = resolve_changeset([hook], git=SubprocessGitClient(cwd=tmp_path))

    # Assert
    assert set(result.files) == {Path("keep.py"), Path("notes.txt")}
    assert result.files_by_hook["lint"] == (Path("keep.py"),)
