"""Workspace discovery — locate and load a monorepo's package configs (STY-0016 / GAT-18).

From a workspace-root ``check.toml``, expand each ``[workspace].packages`` glob and
load the ``check.toml`` of every matched package directory. Pure filesystem discovery
over the given root; a root without a ``[workspace]`` table simply has no packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gatecheck.config import GatecheckConfig, load_config


@dataclass(frozen=True)
class DiscoveredPackage:
    """A workspace package: its directory name, absolute path, and loaded config."""

    name: str
    path: Path
    config: GatecheckConfig


@dataclass(frozen=True)
class Workspace:
    """A discovered workspace: the root config and its packages."""

    root: GatecheckConfig
    root_dir: Path
    packages: tuple[DiscoveredPackage, ...]


def discover_workspace(root_config: Path) -> Workspace:
    """Load ``root_config`` and discover its packages by expanding the workspace globs.

    Each ``[workspace].packages`` glob is expanded relative to the root config's
    directory; every matched directory that contains a ``check.toml`` is loaded via
    ``load_config`` (a broken package config propagates its ``ConfigError``). Results
    are de-duplicated and ordered by path. A root without a ``[workspace]`` table
    yields an empty package set.
    """
    config = load_config(root_config)
    root_dir = root_config.parent.resolve()
    if config.workspace is None:
        return Workspace(root=config, root_dir=root_dir, packages=())

    discovered: dict[Path, DiscoveredPackage] = {}
    for pattern in config.workspace.packages:
        for match in root_dir.glob(pattern):
            package_toml = match / "check.toml"
            if not match.is_dir() or not package_toml.is_file():
                continue
            resolved = match.resolve()
            if resolved in discovered:
                continue
            discovered[resolved] = DiscoveredPackage(
                name=match.name,
                path=resolved,
                config=load_config(package_toml),
            )

    packages = tuple(discovered[path] for path in sorted(discovered))
    return Workspace(root=config, root_dir=root_dir, packages=packages)
