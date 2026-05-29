"""Load and validate a check.toml into a typed config object."""

from __future__ import annotations

from pathlib import Path

from gatecheck.config.schema import GatecheckConfig


def load_config(path: Path) -> GatecheckConfig:
    """Parse `path` (a check.toml) and return a validated GatecheckConfig.

    Implementation lives in STY-0001.
    """
    raise NotImplementedError("load_config — scaffolding only")
