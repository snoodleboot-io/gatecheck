"""Public facade for hooksmith.sources (BUILD-0004-ARCH §2, BUILD-0005-ARCH §2)."""

from __future__ import annotations

from hooksmith.sources.parsed_source import ParsedSource
from hooksmith.sources.parser import parse_source
from hooksmith.sources.project_source import ProjectSource
from hooksmith.sources.pypi_source import PyPISource
from hooksmith.sources.resolved_tool import ResolvedTool
from hooksmith.sources.resolver import resolve_source
from hooksmith.sources.source_resolution_error import SourceResolutionError
from hooksmith.sources.source_spec_error import SourceSpecError
from hooksmith.sources.system_source import SystemSource
from hooksmith.sources.unsupported_source import UnsupportedSource

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
