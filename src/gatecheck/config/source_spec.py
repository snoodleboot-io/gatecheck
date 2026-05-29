"""SourceSpec model — `[sources]` table (BUILD-0001-ARCH §3.1)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceSpec(BaseModel):
    """Pydantic model for the `[sources]` table in check.toml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    default_registry: str | None = Field(default=None, alias="default-registry", min_length=1)
