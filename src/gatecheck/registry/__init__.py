"""Public facade for gatecheck.registry (BUILD-0006-ARCH §2)."""

from __future__ import annotations

from gatecheck.registry.pypi_resolver import resolve_pypi_source
from gatecheck.registry.registry_client import (
    ProjectFile,
    ProjectPage,
    RegistryClient,
    UrllibRegistryClient,
)
from gatecheck.registry.registry_error import RegistryError
from gatecheck.registry.resolved_pypi_source import ResolvedPyPISource

__all__ = [
    "ProjectFile",
    "ProjectPage",
    "RegistryClient",
    "RegistryError",
    "ResolvedPyPISource",
    "UrllibRegistryClient",
    "resolve_pypi_source",
]
