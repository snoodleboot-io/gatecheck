"""Public facade for hooksmith.workspace — monorepo discovery (STY-0016)."""

from __future__ import annotations

from hooksmith.workspace.affected import WorkspaceError, affected_packages, run_affected
from hooksmith.workspace.inheritance import effective_config
from hooksmith.workspace.loader import DiscoveredPackage, Workspace, discover_workspace

__all__ = [
    "DiscoveredPackage",
    "Workspace",
    "WorkspaceError",
    "affected_packages",
    "discover_workspace",
    "effective_config",
    "run_affected",
]
