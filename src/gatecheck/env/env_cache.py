"""env_cache — content-addressed cache mechanics for uv-backed venvs (STY-0008 / GAT-10).

Pure filesystem: cache-root resolution (user cache dir), the per-key venv slot, a
health check, and an atomic temp-build-then-``os.replace`` publish. No subprocess,
no network — the actual venv build is passed in as a ``build`` callback so this
module carries no uv/registry dependency and unit-tests standalone.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path

from gatecheck import venv

_SCHEME_DIR = "env-v1"  # dir-level namespace; matches the cache_key scheme tag


def default_cache_root(environ: Mapping[str, str] | None = None) -> Path:
    """Resolve the user cache root ``$XDG_CACHE_HOME/gatecheck`` (``~/.cache`` fallback)."""
    env = os.environ if environ is None else environ
    xdg = env.get("XDG_CACHE_HOME")
    if xdg:
        base = Path(xdg)
    else:
        home = env.get("HOME")
        base = (Path(home) if home else Path.home()) / ".cache"
    return base / "gatecheck"


def venv_slot(cache_root: Path, key: str) -> Path:
    """The content-addressed venv directory for ``key`` under ``cache_root``."""
    return cache_root / _SCHEME_DIR / key


def is_healthy(slot: Path) -> bool:
    """True when ``slot`` holds a usable venv (its executables dir exists)."""
    return venv.bin_dir(slot).is_dir()


def publish_atomically(build: Callable[[Path], None], cache_root: Path, key: str) -> Path:
    """Return the venv slot for ``key``, building it via ``build`` on a cache miss.

    A healthy existing slot is returned immediately (cache hit — ``build`` is not
    called). Otherwise ``build`` runs against a fresh temp dir under the same scheme
    directory and the result is atomically ``os.replace``-d into the slot. A failed
    build removes the temp and re-raises, so a partial venv is never published; a
    lost publish race (a peer built the same key first) discards the temp and returns
    the peer's slot.
    """
    slot = venv_slot(cache_root, key)
    if is_healthy(slot):
        return slot
    scheme_dir = cache_root / _SCHEME_DIR
    scheme_dir.mkdir(parents=True, exist_ok=True)
    build_dir = Path(tempfile.mkdtemp(dir=scheme_dir, prefix=".building-"))
    try:
        build(build_dir)
    except BaseException:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise
    try:
        os.replace(build_dir, slot)
    except OSError:  # a concurrent builder already published this key
        shutil.rmtree(build_dir, ignore_errors=True)
    return slot
