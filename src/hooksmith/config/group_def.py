"""GroupDef model — `[group.<name>]` table (BUILD-0001-ARCH §3.3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class GroupDef(BaseModel):
    """Pydantic model for a single `[group.<name>]` table in check.toml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    hooks: list[str] = Field(min_length=1)
    parallel: StrictBool = Field(default=False)
    fail_fast: StrictBool = Field(default=False, alias="fail-fast")
    max_workers: int = Field(default=4, alias="max-workers", ge=1)
    on_event: Literal["commit", "push", "commit-msg"] | None = Field(default=None, alias="on-event")

    @field_validator("hooks")
    @classmethod
    def _check_hooks_non_empty_entries(cls, value: list[str]) -> list[str]:
        if any(not entry for entry in value):
            raise ValueError("each entry in 'hooks' must be a non-empty string")
        return value
