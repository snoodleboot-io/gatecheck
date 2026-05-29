"""GatecheckConfig model — top-level check.toml document (BUILD-0001-ARCH §3.4)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from gatecheck.config.group_def import GroupDef
from gatecheck.config.hook_def import HookDef
from gatecheck.config.source_spec import SourceSpec


class GatecheckConfig(BaseModel):
    """Pydantic model for the top-level check.toml document."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    hook: list[HookDef] = Field(default_factory=list)
    group: dict[str, GroupDef] = Field(default_factory=dict)
    sources: SourceSpec | None = Field(default=None)
