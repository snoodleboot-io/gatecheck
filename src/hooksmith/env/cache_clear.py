"""Cache clearing — remove cached environments from the user cache (STY-0027 / GAT-29).

Deletes the content-addressed venv slots under ``<cache_root>/env-v1`` (and, with
``include_uv``, the bootstrapped ``uv`` under ``<cache_root>/bin``). Reports how many
environments were removed and how many bytes were freed. Tolerant of concurrent
writers and a missing cache.
"""

from __future__ import annotations

import contextlib
import shutil
from dataclasses import dataclass
from pathlib import Path

_SCHEME_DIR = "env-v1"
_UV_DIR = "bin"


@dataclass(frozen=True)
class ClearOutcome:
    """The result of clearing the cache."""

    removed: int
    freed_bytes: int


def clear_cache(
    cache_root: Path, *, include_uv: bool = False, dry_run: bool = False
) -> ClearOutcome:
    """Remove cached hook environments under ``cache_root``.

    Each venv slot under ``env-v1`` is counted and removed; ``include_uv`` also
    removes the bootstrapped uv directory (``bin``). ``dry_run`` measures without
    deleting. A missing cache yields ``ClearOutcome(0, 0)``.
    """
    removed = 0
    freed = 0

    scheme_dir = cache_root / _SCHEME_DIR
    if scheme_dir.is_dir():
        for slot in scheme_dir.iterdir():
            if not slot.is_dir():
                continue
            freed += _dir_size(slot)
            removed += 1
            if not dry_run:
                shutil.rmtree(slot, ignore_errors=True)
        if not dry_run:
            _remove_if_empty(scheme_dir)

    if include_uv:
        uv_dir = cache_root / _UV_DIR
        if uv_dir.is_dir():
            freed += _dir_size(uv_dir)
            if not dry_run:
                shutil.rmtree(uv_dir, ignore_errors=True)

    return ClearOutcome(removed=removed, freed_bytes=freed)


def _dir_size(path: Path) -> int:
    """Total size in bytes of the regular files under ``path`` (symlinks not followed)."""
    total = 0
    for child in path.rglob("*"):
        if child.is_file() and not child.is_symlink():
            with contextlib.suppress(OSError):  # a concurrent removal — ignore
                total += child.stat().st_size
    return total


def _remove_if_empty(path: Path) -> None:
    """Remove ``path`` if it has no remaining entries (best-effort)."""
    try:
        next(path.iterdir())
    except StopIteration:
        path.rmdir()
    except OSError:
        pass
