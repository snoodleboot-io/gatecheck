"""Thin import wrapper around the hooksmith_core Rust extension module.

Centralizing the import here gives the Python side a single place to raise a
clear error if the wheel was installed without the native bits, and a single
place to mock during tests that don't need the runner.
"""

from __future__ import annotations

try:
    import hooksmith_core as _core
except ImportError as exc:  # pragma: no cover — only hit in broken installs
    raise ImportError(
        "hooksmith_core (the Rust extension) is not installed. "
        "Reinstall hooksmith from a wheel, or run `maturin develop` in hooksmith-rs/."
    ) from exc

core = _core

__all__ = ["core"]
