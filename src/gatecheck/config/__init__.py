"""Public facade for gatecheck.config (BUILD-0001-ARCH §2, BUILD-0002-ARCH §6)."""

from __future__ import annotations

from gatecheck.config.config_error import ConfigError
from gatecheck.config.dumper import dump_config
from gatecheck.config.gatecheck_config import GatecheckConfig
from gatecheck.config.group_def import GroupDef
from gatecheck.config.hook_def import HookDef
from gatecheck.config.loader import load_config
from gatecheck.config.source_spec import SourceSpec

__all__ = [
    "ConfigError",
    "GatecheckConfig",
    "GroupDef",
    "HookDef",
    "SourceSpec",
    "dump_config",
    "load_config",
]
