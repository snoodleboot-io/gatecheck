"""SourceSpec model — `[sources]` table (BUILD-0001-ARCH §3.1, BUILD-0006-ARCH §7)."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_ALIAS_RE: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]+")


class SourceSpec(BaseModel):
    """Pydantic model for the `[sources]` table in check.toml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    default_registry: str | None = Field(default=None, alias="default-registry", min_length=1)
    extra_registries: dict[str, str] = Field(default_factory=dict, alias="extra-registries")

    @field_validator("extra_registries")
    @classmethod
    def _check_extra_registries(cls, value: dict[str, str]) -> dict[str, str]:
        for alias, url in value.items():
            if _ALIAS_RE.fullmatch(alias) is None:
                raise ValueError(f"registry alias '{alias}' must match [A-Za-z0-9_-]+")
            if not url:
                raise ValueError(f"registry '{alias}' has an empty index URL")
        return value
