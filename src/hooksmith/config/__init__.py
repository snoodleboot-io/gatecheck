"""Public facade for hooksmith.config (BUILD-0001-ARCH §2, BUILD-0002-ARCH §6)."""

from __future__ import annotations

from hooksmith.config.config_error import ConfigError
from hooksmith.config.discovery import discover_config
from hooksmith.config.dumper import dump_config
from hooksmith.config.group_def import GroupDef
from hooksmith.config.hook_def import HookDef
from hooksmith.config.hooksmith_config import HooksmithConfig
from hooksmith.config.loader import load_config
from hooksmith.config.package_spec import PackageSpec
from hooksmith.config.source_spec import SourceSpec
from hooksmith.config.workspace_spec import WorkspaceSpec

__all__ = [
    "ConfigError",
    "GroupDef",
    "HookDef",
    "HooksmithConfig",
    "PackageSpec",
    "SourceSpec",
    "WorkspaceSpec",
    "discover_config",
    "dump_config",
    "load_config",
]
