"""Discover the packages in a workspace and compute the affected set."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    """A monorepo workspace — root plus the per-package configs found beneath it."""

    root: Path

    @classmethod
    def load(cls, root: Path) -> Workspace:
        raise NotImplementedError("Workspace.load — scaffolding only")
