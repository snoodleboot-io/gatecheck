"""ParsedSource union alias over the four source kinds (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from hooksmith.sources.project_source import ProjectSource
from hooksmith.sources.pypi_source import PyPISource
from hooksmith.sources.system_source import SystemSource
from hooksmith.sources.unsupported_source import UnsupportedSource

ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource
