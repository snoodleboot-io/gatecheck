"""git hook installation — wire groups to git events (STY-0022 / GAT-21).

Writes a git hook script per event that runs ``gatecheck run <group>`` for every
group with a matching ``on-event``. Only gatecheck-managed hooks (carrying a marker
line) are overwritten; a pre-existing unmanaged hook is left untouched.
"""

from __future__ import annotations

import stat
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from gatecheck.config import GatecheckConfig
from gatecheck.runner import SubprocessGitClient

_MARKER = "# gatecheck-managed"
# group.on-event value -> git hook filename.
_EVENT_TO_HOOK = {"commit": "pre-commit", "push": "pre-push"}


class HooksLocator(Protocol):
    """Locates the repository's git hooks directory."""

    def hooks_dir(self) -> Path: ...


@dataclass(frozen=True)
class InstallOutcome:
    """The result of installing (or skipping) one git hook file."""

    git_hook: str
    groups: tuple[str, ...]
    status: str  # "installed" | "skipped"
    detail: str


def install_hooks(
    config: GatecheckConfig, *, locator: HooksLocator | None = None
) -> tuple[InstallOutcome, ...]:
    """Install a git hook per event for the groups that declare an ``on-event``.

    Groups sharing an event are combined into one hook script (run in order). An
    existing hook is overwritten only if it is gatecheck-managed; otherwise it is
    skipped and reported. Raises ``GitError`` outside a git repository.
    """
    hooks_dir = (SubprocessGitClient() if locator is None else locator).hooks_dir()
    by_hook = _groups_by_hook(config)

    outcomes: list[InstallOutcome] = []
    for git_hook, groups in by_hook.items():
        path = hooks_dir / git_hook
        if path.exists() and _MARKER not in path.read_text(encoding="utf-8"):
            outcomes.append(
                InstallOutcome(
                    git_hook, groups, "skipped", "existing hook is not gatecheck-managed"
                )
            )
            continue
        _write_hook(path, groups)
        outcomes.append(InstallOutcome(git_hook, groups, "installed", ""))
    return tuple(outcomes)


def _groups_by_hook(config: GatecheckConfig) -> dict[str, tuple[str, ...]]:
    """Map each git hook filename to the groups (in declared order) that target it."""
    by_hook: dict[str, list[str]] = {}
    for name, group in config.group.items():
        if group.on_event is None:
            continue
        git_hook = _EVENT_TO_HOOK[group.on_event]
        by_hook.setdefault(git_hook, []).append(name)
    return {git_hook: tuple(groups) for git_hook, groups in by_hook.items()}


def _write_hook(path: Path, groups: Iterable[str]) -> None:
    """Write an executable gatecheck-managed hook script running each group."""
    lines = ["#!/bin/sh", _MARKER, "set -e"]
    lines += [f"gatecheck run {group}" for group in groups]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def has_on_event_groups(config: GatecheckConfig) -> bool:
    """True when any group declares an ``on-event`` (i.e. there is something to install)."""
    return any(group.on_event is not None for group in config.group.values())
