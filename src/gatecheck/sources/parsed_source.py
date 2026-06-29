"""ParsedSource union alias over the four source kinds (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from gatecheck.sources.project_source import ProjectSource
from gatecheck.sources.pypi_source import PyPISource
from gatecheck.sources.system_source import SystemSource
from gatecheck.sources.unsupported_source import UnsupportedSource

ParsedSource = PyPISource | ProjectSource | SystemSource | UnsupportedSource
