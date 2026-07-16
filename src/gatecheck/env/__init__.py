"""Public facade for gatecheck.env (STY-0007 + STY-0008)."""

from __future__ import annotations

from gatecheck.env.cache_clear import ClearOutcome, clear_cache
from gatecheck.env.cache_explanation import CacheExplanation
from gatecheck.env.env_error import EnvError
from gatecheck.env.manager import EnvManager, ResolvedEnv
from gatecheck.env.sync import SyncOutcome, sync_environments
from gatecheck.env.uv_runner import SubprocessUvRunner, UvRunner

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
