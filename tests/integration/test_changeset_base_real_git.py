"""Integration test: ``--base`` file selection against real git (STY-0040 / GAT-45).

The unit suite drives ``resolve_changeset(base=…)`` through a fake seam. This asserts
the real plumbing — that ``SubprocessGitClient.changed_since`` uses **merge-base**
semantics, so a branch reports only its own changes even when the base has moved on.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from gatecheck.runner import resolve_changeset

pytestmark = pytest.mark.integration

_skip = pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def _commit(message: str) -> None:
    _git("add", "-A")
    _git("commit", "-qm", message)


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)


@_skip
def test_base_reports_only_the_branch_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a base commit, a branch adding one file, then the base moves on.
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    _git("config", "user.email", "t@e.com")
    _git("config", "user.name", "T")

    (repo / "base.py").write_text("x = 1\n", encoding="utf-8")
    _commit("base")
    base_ref = _git("branch", "--show-current")

    _git("checkout", "-qb", "feature")
    (repo / "added.py").write_text("y = 2\n", encoding="utf-8")
    _commit("add on branch")

    # The base branch advances independently — a two-dot diff would wrongly include this.
    _git("checkout", "-q", base_ref)
    (repo / "moved-on.py").write_text("z = 3\n", encoding="utf-8")
    _commit("advance base")
    _git("checkout", "-q", "feature")

    # Act
    changeset = resolve_changeset([], base=base_ref)

    # Assert — only the branch's own file; not the base's later commit, not the
    # file both share.
    assert changeset.files == (Path("added.py"),)


@_skip
def test_base_is_empty_when_branch_adds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a branch with no commits of its own
    repo = tmp_path / "repo"
    _init_repo(repo)
    monkeypatch.chdir(repo)
    _git("config", "user.email", "t@e.com")
    _git("config", "user.name", "T")

    (repo / "base.py").write_text("x = 1\n", encoding="utf-8")
    _commit("base")
    base_ref = _git("branch", "--show-current")
    _git("checkout", "-qb", "feature")

    # Act
    changeset = resolve_changeset([], base=base_ref)

    # Assert
    assert changeset.files == ()
