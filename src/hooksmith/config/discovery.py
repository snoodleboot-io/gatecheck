"""Config discovery — find the check.toml (or pyproject.toml) for a run (GAT-48).

When no ``--config`` is given, hooksmith searches upward from the working directory,
like every other tool in this space. Each directory is checked for a ``check.toml``
first, then a ``pyproject.toml`` carrying a ``[tool.hooksmith]`` table. The walk stops
after the directory that holds ``.git`` (the repo root) so discovery never escapes the
project, falling back to the filesystem root otherwise.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_CHECK_TOML = "check.toml"
_PYPROJECT = "pyproject.toml"


def discover_config(start: Path) -> Path | None:
    """Search ``start`` and its parents for a hooksmith config; return it or ``None``.

    At each directory, a ``check.toml`` wins over a ``pyproject.toml`` with a
    ``[tool.hooksmith]`` table. The search stops after a directory containing ``.git``.
    """
    for directory in _walk_up(start):
        check = directory / _CHECK_TOML
        if check.is_file():
            return check
        pyproject = directory / _PYPROJECT
        if pyproject.is_file() and _has_hooksmith_table(pyproject):
            return pyproject
        if (directory / ".git").exists():
            break  # don't search above the repo root
    return None


def _walk_up(start: Path) -> list[Path]:
    """``start`` and each ancestor, nearest first (resolved to an absolute path)."""
    start = start.resolve()
    return [start, *start.parents]


def _has_hooksmith_table(pyproject: Path) -> bool:
    """True when ``pyproject`` parses and contains a ``[tool.hooksmith]`` table.

    A malformed or unreadable ``pyproject.toml`` is treated as "not a hooksmith config"
    rather than an error — discovery keeps walking. If the user meant to configure
    hooksmith there, ``load_config`` reports the parse error when it reads the file.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return False
    tool = data.get("tool")
    return isinstance(tool, dict) and isinstance(tool.get("hooksmith"), dict)
