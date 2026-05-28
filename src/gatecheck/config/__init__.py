"""Config loading and validation."""

from gatecheck.config.loader import load_config
from gatecheck.config.schema import GatecheckConfig, GroupDef, HookDef, SourceSpec

__all__ = ["GatecheckConfig", "GroupDef", "HookDef", "SourceSpec", "load_config"]
