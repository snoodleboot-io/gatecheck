"""ProjectSource model — the bare `project` source spec (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class ProjectSource(BaseModel):
    """Frozen pydantic model for the project's own activated venv source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["project"] = "project"
