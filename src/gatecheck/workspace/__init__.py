"""Public facade for gatecheck.workspace — monorepo discovery (STY-0016)."""

from __future__ import annotations

from gatecheck.workspace.inheritance import effective_config
from gatecheck.workspace.loader import DiscoveredPackage, Workspace, discover_workspace

__all__ = [
    "DiscoveredPackage",
    "Workspace",
    "discover_workspace",
    "effective_config",
]
