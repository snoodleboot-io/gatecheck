"""resolve_source — locate a ParsedSource's tool as a concrete executable (BUILD-0005-ARCH §4).

Filesystem lookup only: no network, no subprocess, no writes (AC-9). Given the
same ``(source, tool, PATH, VIRTUAL_ENV, workspace_root, filesystem state)`` the
result is deterministic (AC-10). Only ``SystemSource`` / ``ProjectSource``
resolve; ``PyPISource`` / ``UnsupportedSource`` raise ``SourceResolutionError``.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from gatecheck import venv
from gatecheck.sources.parsed_source import ParsedSource
from gatecheck.sources.project_source import ProjectSource
from gatecheck.sources.pypi_source import PyPISource
from gatecheck.sources.resolved_tool import ResolvedTool
from gatecheck.sources.source_resolution_error import SourceResolutionError
from gatecheck.sources.system_source import SystemSource
from gatecheck.sources.unsupported_source import UnsupportedSource


def resolve_source(
    source: ParsedSource,
    tool: str,
    *,
    workspace_root: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> ResolvedTool:
    """Resolve ``tool`` for ``source`` into a concrete, absolute ``ResolvedTool``.

    Defaults are resolved inside the body — ``environ`` falls back to
    ``os.environ`` and ``workspace_root`` to ``Path.cwd()``. Raises
    ``SourceResolutionError`` when the tool cannot be located, or when ``source``
    is a ``PyPISource`` / ``UnsupportedSource`` (handled elsewhere / unsupported).
    """
    env = os.environ if environ is None else environ
    root = Path.cwd() if workspace_root is None else workspace_root

    match source:
        case SystemSource():
            return _resolve_system(tool, env)
        case ProjectSource():
            return _resolve_project(tool, root, env)
        case PyPISource():
            raise SourceResolutionError(
                tool,
                "pypi",
                "pypi source resolution is delegated to Environments (STY-0006), not handled here",
            )
        case UnsupportedSource(scheme=scheme):
            raise SourceResolutionError(
                tool,
                "unsupported",
                f"'{scheme}' sources are not supported",
            )


def _resolve_system(tool: str, environ: Mapping[str, str]) -> ResolvedTool:
    """Locate ``tool`` on ``PATH`` via ``shutil.which``.

    ``PATH`` is read only from ``environ`` (falling back to ``os.defpath`` when
    absent), never from the ambient process environment — so resolution stays a
    deterministic function of the injected ``environ`` (AC-10).
    """
    located = shutil.which(tool, path=environ.get("PATH", os.defpath))
    if located is None:
        raise SourceResolutionError(tool, "system", "not found on PATH")
    return ResolvedTool(tool=tool, executable=Path(located).resolve(), origin="system")


def _resolve_project(tool: str, root: Path, environ: Mapping[str, str]) -> ResolvedTool:
    """Locate ``tool`` in the project's existing venv (active VIRTUAL_ENV, then <root>/.venv).

    Honors the platform venv layout: ``bin`` on POSIX, ``Scripts`` on Windows, and
    the ``.exe`` / ``.bat`` / ``.cmd`` executable variants on Windows.
    """
    bases: list[Path] = []
    virtual_env = environ.get("VIRTUAL_ENV")
    if virtual_env:
        bases.append(venv.bin_dir(Path(virtual_env)))
    bases.append(venv.bin_dir(root / ".venv"))

    for base in bases:
        for name in venv.executable_candidates(tool):
            candidate = base / name
            if venv.is_executable(candidate):
                return ResolvedTool(tool=tool, executable=candidate.resolve(), origin="project")

    checked = venv.bin_dir_name()
    raise SourceResolutionError(
        tool,
        "project",
        f"not found in project environment "
        f"(checked $VIRTUAL_ENV/{checked} and <workspace_root>/.venv/{checked})",
    )
