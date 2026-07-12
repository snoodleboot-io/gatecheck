"""Public facade for gatecheck.migration — pre-commit → check.toml (STY-0019)."""

from __future__ import annotations

from gatecheck.migration.migration_error import MigrationError
from gatecheck.migration.parser import parse_precommit_config
from gatecheck.migration.precommit_config import PreCommitConfig, PreCommitHook, PreCommitRepo

__all__ = [
    "MigrationError",
    "PreCommitConfig",
    "PreCommitHook",
    "PreCommitRepo",
    "parse_precommit_config",
]
