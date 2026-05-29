"""Public facade for gatecheck.config (BUILD-0001-ARCH §2)."""

from __future__ import annotations

from gatecheck.config.gatecheck_config import GatecheckConfig
from gatecheck.config.group_def import GroupDef
from gatecheck.config.hook_def import HookDef
from gatecheck.config.loader import load_config
from gatecheck.config.source_spec import SourceSpec

__all__ = ["GatecheckConfig", "GroupDef", "HookDef", "SourceSpec", "load_config"]
