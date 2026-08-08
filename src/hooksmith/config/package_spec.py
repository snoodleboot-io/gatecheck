"""PackageSpec model — `[package]` table (STY-0016 / GAT-18)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from hooksmith.config.workspace_spec import InheritMode


class PackageSpec(BaseModel):
    """Pydantic model for the `[package]` table (workspace-package config only)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    depends_on: list[str] = Field(default_factory=list, alias="depends-on")
    python: str | None = Field(default=None, min_length=1)
    # None → inherit the workspace default inherit mode.
    inherit: InheritMode | None = Field(default=None)
