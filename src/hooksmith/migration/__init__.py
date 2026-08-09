"""Public facade for hooksmith.migration — pre-commit → check.toml (STY-0019)."""

from __future__ import annotations

from hooksmith.migration.mapper import map_precommit
from hooksmith.migration.migration_error import MigrationError
from hooksmith.migration.parser import parse_precommit_config
from hooksmith.migration.precommit_config import PreCommitConfig, PreCommitHook, PreCommitRepo

__all__ = [
    "MigrationError",
    "PreCommitConfig",
    "PreCommitHook",
    "PreCommitRepo",
    "map_precommit",
    "parse_precommit_config",
]
