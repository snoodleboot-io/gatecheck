"""Load and validate a check.toml into a typed GatecheckConfig (BUILD-0001-ARCH §4)."""

from __future__ import annotations

import stat
import tomllib
from pathlib import Path

from gatecheck.config.gatecheck_config import GatecheckConfig


def load_config(path: Path) -> GatecheckConfig:
    """Parse `path` (a check.toml) and return a validated GatecheckConfig."""
    st = path.stat()
    if not stat.S_ISREG(st.st_mode):
        raise OSError(f"check.toml must be a regular file, got: {path}")
    # 1 MiB cap — real configs are < 10 KiB; this bounds parse-time DoS surface.
    if st.st_size > 1 << 20:
        raise OSError(f"check.toml exceeds 1 MiB (was {st.st_size} bytes): {path}")
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    return GatecheckConfig.model_validate(data)
