"""EnvManager — resolve a HookDef to an executable environment (STY-0007 + STY-0008).

``from = "project"`` / ``from = "system"`` reuse an existing interpreter or binary
via ``resolve_source`` (non-venv path, STY-0007). ``pypi:`` / ``pypi+alias:`` pin the
requirement (``registry.resolve_pypi_source``) and build — or reuse from a
content-addressed cache — a uv-backed venv (STY-0008). ``UnsupportedSource`` raises
``EnvError``. The non-venv path is pure/hermetic; the pypi path touches the network
(pinning) and, on a cache miss, a ``uv`` subprocess (behind the injectable
``UvRunner`` seam).
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from gatecheck import venv
from gatecheck.command import tokenize
from gatecheck.config import SourceSpec
from gatecheck.config.hook_def import HookDef
from gatecheck.env.cache_explanation import CacheExplanation
from gatecheck.env.env_cache import default_cache_root, is_healthy, publish_atomically, venv_slot
from gatecheck.env.env_error import EnvError
from gatecheck.env.uv_bootstrap import UvBootstrapError
from gatecheck.env.uv_runner import SubprocessUvRunner, UvBuildError, UvNotFound, UvRunner
from gatecheck.offline import is_offline
from gatecheck.registry import RegistryClient, ResolvedPyPISource, resolve_pypi_source
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
    """Owns the per-hook environment cache (non-venv path + uv-backed pypi venvs)."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        environ: Mapping[str, str] | None = None,
        *,
        sources: SourceSpec | None = None,
        cache_root: Path | None = None,
        client: RegistryClient | None = None,
        uv_runner: UvRunner | None = None,
    ) -> None:
        self._workspace_root = workspace_root
        self._environ = environ
        self._sources = sources
        self._cache_root = cache_root
        self._client = client
        self._uv_runner = uv_runner
        self._offline = is_offline(environ)

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        """Resolve ``hook`` to a ``ResolvedEnv`` (an executable environment).

        Classifies ``hook.from_`` and dispatches on its kind. ``SystemSource`` /
        ``ProjectSource`` are located via ``resolve_source`` (non-venv path);
        ``PyPISource`` pins + builds a cached uv venv; ``UnsupportedSource`` raises
        ``EnvError``. ``SourceSpecError`` (malformed ``from``), ``SourceResolutionError``
        (tool absent), and ``RegistryError`` (pinning/network) propagate unwrapped.
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
                return self._resolve_pypi(hook, source, tool)
            case UnsupportedSource(scheme=scheme):
                raise EnvError(hook.id, f"'{scheme}' sources are not supported")

    def explain(self, hook: HookDef) -> CacheExplanation:
        """Explain ``hook``'s cache state without building anything (read-only).

        Derives the same ``cache_key`` as ``resolve`` and inspects the cache, but
        never creates or mutates a directory and never spawns ``uv``. For ``pypi``
        it pins the requirement (which may query the registry) to derive the key;
        the status is ``hit`` when the venv slot already exists, else ``miss``. For
        ``system`` / ``project`` no environment is cached, so the status is
        ``not-applicable``. ``SourceSpecError`` / ``SourceResolutionError`` /
        ``RegistryError`` propagate unwrapped; ``UnsupportedSource`` raises ``EnvError``.
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
                return CacheExplanation(
                    hook_id=hook.id,
                    source_kind=resolved.origin,
                    source_summary=f"{resolved.origin} tool '{tool}' at {resolved.executable}",
                    cache_key=self._cache_key(resolved),
                    key_material=(_CACHE_KEY_SCHEME, resolved.origin, str(resolved.executable)),
                    cache_dir=str(resolved.executable.parent),
                    status="not-applicable",
                    reason="project/system sources reuse an existing binary; no environment is cached",
                )
            case PyPISource():
                pinned = resolve_pypi_source(
                    source, self._sources, client=self._client, offline=self._offline
                )
                key = self._pypi_cache_key(pinned)
                cache_root = (
                    self._cache_root
                    if self._cache_root is not None
                    else default_cache_root(self._environ)
                )
                slot = venv_slot(cache_root, key)
                hit = is_healthy(slot)
                return CacheExplanation(
                    hook_id=hook.id,
                    source_kind="pypi",
                    source_summary=f"pypi {pinned.name}=={pinned.version} @ {pinned.index_url}",
                    cache_key=key,
                    key_material=(
                        _CACHE_KEY_SCHEME,
                        "pypi",
                        pinned.name,
                        pinned.version,
                        pinned.index_url,
                    ),
                    cache_dir=str(slot),
                    status="hit" if hit else "miss",
                    reason=(
                        "cached venv present — reused on the next run"
                        if hit
                        else "no cached venv yet — built on the next run"
                    ),
                )
            case UnsupportedSource(scheme=scheme):
                raise EnvError(hook.id, f"'{scheme}' sources are not supported")

    def _resolve_pypi(self, hook: HookDef, source: PyPISource, tool: str) -> ResolvedEnv:
        """Pin ``source`` and build (or reuse) a uv-backed venv; return its ``ResolvedEnv``.

        ``RegistryError`` from pinning propagates unwrapped; ``uv`` failures
        (``UvNotFound`` / ``UvBuildError``) and a venv missing ``tool`` map to
        ``EnvError`` naming the hook.
        """
        pinned = resolve_pypi_source(
            source, self._sources, client=self._client, offline=self._offline
        )
        key = self._pypi_cache_key(pinned)
        cache_root = (
            self._cache_root if self._cache_root is not None else default_cache_root(self._environ)
        )
        if self._offline and not is_healthy(venv_slot(cache_root, key)):
            raise EnvError(
                hook.id,
                f"offline: no cached environment for '{pinned.name}=={pinned.version}'; "
                "run 'gatecheck sync' while online first to warm the cache",
            )
        runner = (
            self._uv_runner
            if self._uv_runner is not None
            else SubprocessUvRunner(self._environ, cache_root=cache_root)
        )
        try:
            slot = publish_atomically(lambda dest: runner.build_venv(pinned, dest), cache_root, key)
        except UvNotFound as exc:
            raise EnvError(
                hook.id,
                "uv is required to build pypi environments but is unavailable "
                "(set GATECHECK_UV, install uv, or allow auto-bootstrap)",
            ) from exc
        except UvBootstrapError as exc:
            raise EnvError(
                hook.id,
                f"could not auto-bootstrap uv to build the environment for "
                f"'{pinned.name}=={pinned.version}': {exc}",
            ) from exc
        except UvBuildError as exc:
            raise EnvError(
                hook.id,
                f"uv failed to build the environment for '{pinned.name}=={pinned.version}': {exc}",
            ) from exc
        bin_dir = venv.bin_dir(slot)
        if not any((bin_dir / name).exists() for name in venv.executable_candidates(tool)):
            raise EnvError(
                hook.id,
                f"tool '{tool}' is not present in the built environment for "
                f"'{pinned.name}=={pinned.version}'",
            )
        return ResolvedEnv(bin_dir=bin_dir, cache_key=key)

    def _derive_tool(self, hook: HookDef) -> str:
        """Derive the bare tool name as ``shlex.split(hook.run)[0]`` (POSIX tokenization).

        Raises ``EnvError`` when ``run`` yields no tokens (whitespace-only) or
        cannot be tokenized (unbalanced quotes).
        """
        try:
            tokens = tokenize(hook.run)
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

    def _pypi_cache_key(self, pinned: ResolvedPyPISource) -> str:
        """Derive the 64-char SHA-256 cache key over the pinned distribution.

        Reuses the ``env-v1`` scheme but keys on ``name`` + ``version`` + ``index_url``
        (content-addressing the venv), distinct from the non-venv key by the ``pypi``
        field. ``sha256`` is an install-integrity input, not a key input.
        """
        material = "\n".join(
            [_CACHE_KEY_SCHEME, "pypi", pinned.name, pinned.version, pinned.index_url]
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
