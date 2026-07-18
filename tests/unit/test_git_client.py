"""Unit tests for gatecheck.runner.SubprocessGitClient (STY-0011 / GAT-13).

Hermetic — ``subprocess.run`` is patched at the module boundary; no real git.
Covers the argv for staged / tracked queries, NUL-delimited parsing (including
empty output), and ``GitError`` on a non-zero exit and a missing binary. AAA.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from gatecheck.runner import GitError, SubprocessGitClient
from gatecheck.runner import git_client as git_client_module


def _patch_run(monkeypatch: pytest.MonkeyPatch, recorded: list[list[str]], result: object) -> None:
    def fake_run(argv: list[str], **kwargs: object) -> object:
        recorded.append(argv)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(git_client_module.subprocess, "run", fake_run)


def test_staged_files_argv_and_nul_split(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(
        monkeypatch, recorded, SimpleNamespace(returncode=0, stdout="a.py\x00b.txt\x00", stderr="")
    )
    # Act
    files = SubprocessGitClient().staged_files()
    # Assert
    assert files == ("a.py", "b.txt")
    assert recorded[0] == ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"]


def test_tracked_files_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(monkeypatch, recorded, SimpleNamespace(returncode=0, stdout="", stderr=""))
    # Act
    files = SubprocessGitClient().tracked_files()
    # Assert — empty output → empty tuple (no spurious "" entry)
    assert files == ()
    assert recorded[0] == ["git", "ls-files", "-z"]


def test_current_branch_argv_and_strip(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(monkeypatch, recorded, SimpleNamespace(returncode=0, stdout="main\n", stderr=""))
    # Act
    branch = SubprocessGitClient().current_branch()
    # Assert
    assert branch == "main"
    assert recorded[0] == ["git", "branch", "--show-current"]


def test_current_branch_empty_when_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — detached HEAD → empty output, exit 0
    recorded: list[list[str]] = []
    _patch_run(monkeypatch, recorded, SimpleNamespace(returncode=0, stdout="\n", stderr=""))
    # Act
    branch = SubprocessGitClient().current_branch()
    # Assert
    assert branch == ""


def test_current_branch_nonzero_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(
        monkeypatch, recorded, SimpleNamespace(returncode=128, stdout="", stderr="fatal: boom")
    )
    # Act / Assert
    with pytest.raises(GitError, match="cannot determine current branch"):
        SubprocessGitClient().current_branch()


def test_nonzero_exit_raises_git_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(
        monkeypatch,
        recorded,
        SimpleNamespace(returncode=128, stdout="", stderr="not a git repository"),
    )
    # Act / Assert
    with pytest.raises(GitError, match="not a git repository"):
        SubprocessGitClient().staged_files()


def test_missing_git_binary_raises_git_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    recorded: list[list[str]] = []
    _patch_run(monkeypatch, recorded, FileNotFoundError("no git"))
    # Act / Assert
    with pytest.raises(GitError, match="git executable not found"):
        SubprocessGitClient().tracked_files()
