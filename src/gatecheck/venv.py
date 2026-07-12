"""Cross-platform virtualenv layout helpers (STY-0023 / GAT-25).

The single place the ``bin`` vs ``Scripts`` (and ``python`` vs ``python.exe``)
difference lives, so every consumer — env cache, uv builder, source resolver —
resolves venv executables the same way on POSIX and Windows.
"""

from __future__ import annotations

import os
from pathlib import Path


def _is_windows() -> bool:
    return os.name == "nt"


def bin_dir_name() -> str:
    """The venv's executables sub-directory: ``Scripts`` on Windows, else ``bin``."""
    return "Scripts" if _is_windows() else "bin"


def bin_dir(venv_root: Path) -> Path:
    """The venv's executables directory (``<venv>/bin`` or ``<venv>/Scripts``)."""
    return venv_root / bin_dir_name()


def python_executable(venv_root: Path) -> Path:
    """The venv's Python interpreter (``bin/python`` or ``Scripts/python.exe``)."""
    return bin_dir(venv_root) / ("python.exe" if _is_windows() else "python")


def executable_candidates(tool: str) -> tuple[str, ...]:
    """Candidate filenames for ``tool`` — bare on POSIX; also ``.exe`` / ``.bat`` / ``.cmd`` on Windows."""
    if _is_windows():
        return (tool, f"{tool}.exe", f"{tool}.bat", f"{tool}.cmd")
    return (tool,)


def is_executable(path: Path) -> bool:
    """True when ``path`` is a runnable file (exec bit on POSIX; existence on Windows)."""
    if not path.is_file():
        return False
    return True if _is_windows() else os.access(path, os.X_OK)
