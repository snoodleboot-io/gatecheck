"""PyPISource model — a `pypi:` / `pypi+<alias>:` source spec (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PyPISource(BaseModel):
    """Frozen pydantic model for a PyPI source.

    ``requirement`` carries the spec text verbatim (not PEP 508 validated).
    ``registry`` is the ``[sources]`` alias name, or ``None`` for the default
    registry; it is not resolved against ``[sources]`` here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["pypi"] = "pypi"
    requirement: str = Field(min_length=1)
    registry: str | None = None
