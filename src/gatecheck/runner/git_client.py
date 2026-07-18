"""GitClient — the git boundary for changeset resolution (STY-0011 / GAT-13).

``GitClient`` is a single injectable ``typing.Protocol`` (mirroring the
``RegistryClient`` / ``UvRunner`` seams) so changeset resolution unit-tests against a
fake — no real repository required. ``SubprocessGitClient`` is the default impl and
the only place ``git`` is invoked; it raises ``GitError`` when git is missing or
exits non-zero. Paths are returned repo-root-relative and POSIX-style, exactly as
git emits them, parsed from NUL-delimited (``-z``) output.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Protocol


class GitError(Exception):
    """Raised when a git query fails (git absent, not a repository, non-zero exit)."""


class GitClient(Protocol):
    """The injectable git boundary: enumerate the changeset's candidate files."""

    def staged_files(self) -> tuple[str, ...]: ...

    def tracked_files(self) -> tuple[str, ...]: ...

    def current_branch(self) -> str: ...


class SubprocessGitClient:
    """Default ``GitClient`` over the ``git`` CLI (NUL-delimited output)."""

    def __init__(self, cwd: Path | None = None) -> None:
        self._cwd = cwd  # None → the current working directory

    def staged_files(self) -> tuple[str, ...]:
        """Return staged, non-deleted paths (added/copied/modified/renamed)."""
        return self._run(["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"])

    def tracked_files(self) -> tuple[str, ...]:
        """Return every tracked path (for ``--all-files``)."""
        return self._run(["git", "ls-files", "-z"])

    def current_branch(self) -> str:
        """Return the current branch name (empty when detached).

        Uses ``git branch --show-current``, which succeeds on an unborn branch (a
        repo with no commits yet) and returns the empty string on a detached HEAD.
        """
        try:
            completed = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=False,
                cwd=self._cwd,
            )
        except FileNotFoundError as exc:
            raise GitError(f"git executable not found: {exc}") from exc
        if completed.returncode != 0:
            raise GitError(f"cannot determine current branch: {completed.stderr.strip()}")
        return completed.stdout.strip()

    def hooks_dir(self) -> Path:
        """Return the repository's git hooks directory (``git rev-parse --git-path hooks``)."""
        try:
            completed = subprocess.run(
                ["git", "rev-parse", "--git-path", "hooks"],
                capture_output=True,
                text=True,
                check=False,
                cwd=self._cwd,
            )
        except FileNotFoundError as exc:
            raise GitError(f"git executable not found: {exc}") from exc
        if completed.returncode != 0:
            raise GitError(f"not a git repository: {completed.stderr.strip()}")
        hooks = completed.stdout.strip()
        base = self._cwd if self._cwd is not None else Path.cwd()
        path = Path(hooks)
        return path if path.is_absolute() else base / path

    def _run(self, argv: list[str]) -> tuple[str, ...]:
        """Run ``argv`` and split its NUL-delimited stdout; raise ``GitError`` on failure."""
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, check=False, cwd=self._cwd
            )
        except FileNotFoundError as exc:
            raise GitError(f"git executable not found: {exc}") from exc
        if completed.returncode != 0:
            raise GitError(
                f"`{' '.join(argv)}` failed ({completed.returncode}): {completed.stderr.strip()}"
            )
        return tuple(path for path in completed.stdout.split("\0") if path)
