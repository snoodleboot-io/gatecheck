"""WorkspaceSpec model — `[workspace]` table (STY-0016 / GAT-18)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

InheritMode = Literal["merge", "override", "none"]


class WorkspaceSpec(BaseModel):
    """Pydantic model for the `[workspace]` table (workspace-root config only)."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    packages: list[str] = Field(min_length=1)
    inherit: InheritMode = Field(default="merge")

    @field_validator("packages")
    @classmethod
    def _check_non_empty_entries(cls, value: list[str]) -> list[str]:
        if any(not entry for entry in value):
            raise ValueError("each entry in 'packages' must be a non-empty glob/path")
        return value
