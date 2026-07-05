"""EnvManager — resolve a HookDef to an executable environment (BUILD-0007-ARCH §5/§6).

The non-venv path only: ``from = "project"`` / ``from = "system"`` reuse an
existing interpreter or binary via ``resolve_source``; ``pypi:`` / ``pypi+alias:``
and unsupported schemes raise ``EnvError``. Pure and hermetic — no subprocess, no
network, no venv creation, no filesystem writes (venv-backed ``pypi`` is STY-0008).
"""

from __future__ import annotations

import hashlib
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from gatecheck.config.hook_def import HookDef
from gatecheck.env.env_error import EnvError
from gatecheck.sources import (
    ProjectSource,
    PyPISource,
    ResolvedTool,
    SystemSource,
    UnsupportedSource,
    parse_source,
    resolve_source,
)

_CACHE_KEY_SCHEME = "env-v1"


@dataclass(frozen=True)
class ResolvedEnv:
    """An environment ready to execute a hook's command."""

    bin_dir: Path
    cache_key: str


class EnvManager:
    """Owns the per-hook environment cache (non-venv path; pypi deferred to STY-0008)."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._environ = environ

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        """Resolve ``hook`` to a ``ResolvedEnv`` (an executable environment).

        Classifies ``hook.from_`` and dispatches on its kind. ``SystemSource`` /
        ``ProjectSource`` are located via ``resolve_source`` (the injected
        ``workspace_root`` / ``environ`` seams forwarded verbatim); ``PyPISource``
        and unsupported schemes raise ``EnvError``. A ``SourceSpecError`` (malformed
        ``from``) or ``SourceResolutionError`` (tool absent) propagates unwrapped.
        """
        source = parse_source(hook.from_)
        tool = self._derive_tool(hook)
        match source:
            case SystemSource() | ProjectSource():
                resolved = resolve_source(
                    source,
                    tool,
                    workspace_root=self._workspace_root,
                    environ=self._environ,
                )
                return ResolvedEnv(
                    bin_dir=resolved.executable.parent,
                    cache_key=self._cache_key(resolved),
                )
            case PyPISource():
                raise EnvError(
                    hook.id,
                    "environment creation for pypi sources is deferred to STY-0008",
                )
            case UnsupportedSource(scheme=scheme):
                raise EnvError(hook.id, f"'{scheme}' sources are not supported")

    def _derive_tool(self, hook: HookDef) -> str:
        """Derive the bare tool name as ``shlex.split(hook.run)[0]`` (POSIX tokenization).

        Raises ``EnvError`` when ``run`` yields no tokens (whitespace-only) or
        cannot be tokenized (unbalanced quotes).
        """
        try:
            tokens = shlex.split(hook.run)
        except ValueError:  # unbalanced quotes, etc.
            raise EnvError(hook.id, f"cannot derive a tool name from run = '{hook.run}'") from None
        if not tokens:
            raise EnvError(hook.id, f"cannot derive a tool name from run = '{hook.run}'")
        return tokens[0]

    def _cache_key(self, resolved: ResolvedTool) -> str:
        """Derive the 64-char SHA-256 cache key over (scheme, origin, executable path).

        Hashing ``origin`` keeps the same binary reached two ways (project vs system)
        keyed distinctly; the ``env-v1`` scheme tag namespaces the derivation.
        """
        material = "\n".join([_CACHE_KEY_SCHEME, resolved.origin, str(resolved.executable)])
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
