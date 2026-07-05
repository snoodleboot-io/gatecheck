"""Resolve a HookDef to an executable environment.

Backed by `uv` for venv creation when the source is a PyPI/private spec.
For `from = "project"` and `from = "system"`, this returns a reference to
the existing interpreter or binary without creating a new env.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from gatecheck.config.hook_def import HookDef


@dataclass(frozen=True)
class ResolvedEnv:
    """An environment ready to execute a hook's command."""

    bin_dir: Path
    cache_key: str


class EnvManager:
    """Owns the per-hook environment cache."""

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        raise NotImplementedError("EnvManager.resolve — scaffolding only")
