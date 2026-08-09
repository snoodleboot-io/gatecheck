"""Public facade for hooksmith.registry (BUILD-0006-ARCH §2)."""

from __future__ import annotations

from hooksmith.registry.pypi_resolver import resolve_pypi_source
from hooksmith.registry.registry_client import (
    ProjectFile,
    ProjectPage,
    RegistryClient,
    UrllibRegistryClient,
)
from hooksmith.registry.registry_error import RegistryError
from hooksmith.registry.resolved_pypi_source import ResolvedPyPISource

__all__ = [
    "ProjectFile",
    "ProjectPage",
    "RegistryClient",
    "RegistryError",
    "ResolvedPyPISource",
    "UrllibRegistryClient",
    "resolve_pypi_source",
]
