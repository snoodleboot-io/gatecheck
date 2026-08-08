"""Public facade for hooksmith.env (STY-0007 + STY-0008)."""

from __future__ import annotations

from hooksmith.env.cache_clear import ClearOutcome, clear_cache
from hooksmith.env.cache_explanation import CacheExplanation
from hooksmith.env.env_error import EnvError
from hooksmith.env.manager import EnvManager, ResolvedEnv
from hooksmith.env.sync import SyncOutcome, sync_environments
from hooksmith.env.uv_runner import SubprocessUvRunner, UvRunner

__all__ = [
    "CacheExplanation",
    "ClearOutcome",
    "EnvError",
    "EnvManager",
    "ResolvedEnv",
    "SubprocessUvRunner",
    "SyncOutcome",
    "UvRunner",
    "clear_cache",
    "sync_environments",
]
