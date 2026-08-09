"""SystemSource model — the bare `system` source spec (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class SystemSource(BaseModel):
    """Frozen pydantic model for the raw-PATH (no env management) source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["system"] = "system"
