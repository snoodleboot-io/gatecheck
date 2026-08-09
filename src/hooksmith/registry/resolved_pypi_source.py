"""ResolvedPyPISource model — a pypi source pinned to an exact version (BUILD-0006-ARCH §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResolvedPyPISource(BaseModel):
    """A pypi source pinned to an exact version against a known index (BUILD-0006-ARCH §3).

    Output value object produced by ``resolve_pypi_source`` — not a member of the
    ``ParsedSource`` union. The load-bearing contract is ``name`` + ``version`` +
    ``index_url`` (enough to install ``name==version --index-url <index_url>``); the
    optional ``sha256`` / ``url`` / ``filename`` are best-effort artifact metadata for
    a single *representative* file (display / ``cache why``), ``None`` when unavailable.
    They are not used for installation — hooksmith installs by exact version and lets
    uv resolve the tree; full-tree hash verification would need a lockfile (BUG-0006).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pypi"] = "pypi"
    requirement: str
    name: str
    version: str
    index_url: str
    registry: str | None = None
    sha256: str | None = None
    url: str | None = None
    filename: str | None = None
