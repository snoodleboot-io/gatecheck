"""ResolvedTool model — a source kind resolved to a concrete executable (BUILD-0005-ARCH §3)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ResolvedTool(BaseModel):
    """A source kind resolved to a concrete, absolute executable.

    Output value object produced by ``resolve_source`` — not a member of the
    ``ParsedSource`` discriminated union. ``executable`` is always the
    ``Path(...).resolve()``-d absolute path; ``origin`` records which rule fired
    (only the two resolvable kinds appear).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tool: str
    executable: Path
    origin: Literal["project", "system"]
