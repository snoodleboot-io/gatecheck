"""UnsupportedSource model — recognized-but-unsupported schemes (BUILD-0004-ARCH §3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class UnsupportedSource(BaseModel):
    """Frozen pydantic model for a recognized scheme not yet supported in FEAT-0002.

    ``local:`` / ``git:`` / ``docker:`` parse cleanly to this so the caller can
    emit a "not yet supported" message rather than "unknown source". The payload
    after the scheme is not parsed in STY-0004 (that is STY-0006).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["unsupported"] = "unsupported"
    scheme: Literal["local", "git", "docker"]
