"""Public facade for gatecheck.sources (BUILD-0004-ARCH §2, BUILD-0005-ARCH §2)."""

from __future__ import annotations

from gatecheck.sources.parsed_source import ParsedSource
from gatecheck.sources.parser import parse_source
from gatecheck.sources.project_source import ProjectSource
from gatecheck.sources.pypi_source import PyPISource
from gatecheck.sources.resolved_tool import ResolvedTool
from gatecheck.sources.resolver import resolve_source
from gatecheck.sources.source_resolution_error import SourceResolutionError
from gatecheck.sources.source_spec_error import SourceSpecError
from gatecheck.sources.system_source import SystemSource
from gatecheck.sources.unsupported_source import UnsupportedSource

__all__ = [
    "ParsedSource",
    "ProjectSource",
    "PyPISource",
    "ResolvedTool",
    "SourceResolutionError",
    "SourceSpecError",
    "SystemSource",
    "UnsupportedSource",
    "parse_source",
    "resolve_source",
]
