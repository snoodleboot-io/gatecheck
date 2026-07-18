"""Changeset resolution — the files each hook runs against (STY-0011 / GAT-13).

Determines the run's file set (staged by default, all tracked with ``all_files``)
and the per-hook subset each hook receives after applying its ``files`` glob and
``pass_files``. Pure over the injected ``GitClient`` + the hooks — no argv assembly,
no subprocess of its own beyond the git query behind the seam.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from gatecheck.config.hook_def import HookDef
from gatecheck.runner.git_client import GitClient, SubprocessGitClient


@dataclass(frozen=True)
class Changeset:
    """The resolved changeset and the files routed to each hook."""

    files: tuple[Path, ...]
    files_by_hook: dict[str, tuple[Path, ...]]


def resolve_changeset(
    hooks: Sequence[HookDef],
    *,
    all_files: bool = False,
    git: GitClient | None = None,
) -> Changeset:
    """Resolve the changeset and route files to each hook.

    The base file set is every tracked file (``all_files=True``) or the staged files
    (default), queried via ``git`` (raises ``GitError`` on failure). Each hook then
    receives no files when ``pass_files`` is false, the whole changeset when its
    ``files`` glob is unset, or the glob-matching subset otherwise.
    """
    client = SubprocessGitClient() if git is None else git
    raw = client.tracked_files() if all_files else client.staged_files()
    files = tuple(Path(path) for path in raw)
    return Changeset(files=files, files_by_hook=route_files(hooks, files))


def route_files(hooks: Sequence[HookDef], files: Sequence[Path]) -> dict[str, tuple[Path, ...]]:
    """Route ``files`` to each hook by ``pass_files`` + the ``files`` glob (pure, no git)."""
    materialized = tuple(files)
    return {hook.id: _files_for_hook(hook, materialized) for hook in hooks}


def _files_for_hook(hook: HookDef, files: tuple[Path, ...]) -> tuple[Path, ...]:
    """Select the files ``hook`` receives (``pass_files`` + ``files``/``exclude`` globs)."""
    if not hook.pass_files:
        return ()
    if hook.files is None:
        selected = files
    else:
        selected = tuple(f for f in files if fnmatch.fnmatchcase(f.as_posix(), hook.files))
    if hook.exclude is not None:
        selected = tuple(f for f in selected if not fnmatch.fnmatchcase(f.as_posix(), hook.exclude))
    return selected
