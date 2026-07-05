"""Public facade for gatecheck.env (BUILD-0007-ARCH §2)."""

from __future__ import annotations

from gatecheck.env.env_error import EnvError
from gatecheck.env.manager import EnvManager, ResolvedEnv

__all__ = [
    "EnvError",
    "EnvManager",
    "ResolvedEnv",
]
