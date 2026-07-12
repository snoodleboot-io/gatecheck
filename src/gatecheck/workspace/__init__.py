"""Public facade for gatecheck.workspace — monorepo discovery (STY-0016)."""

from __future__ import annotations

from gatecheck.workspace.affected import WorkspaceError, affected_packages, run_affected
from gatecheck.workspace.inheritance import effective_config
from gatecheck.workspace.loader import DiscoveredPackage, Workspace, discover_workspace

__all__ = [
    "DiscoveredPackage",
    "Workspace",
    "WorkspaceError",
    "affected_packages",
    "discover_workspace",
    "effective_config",
    "run_affected",
]
