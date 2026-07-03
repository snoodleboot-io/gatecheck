"""Thin import wrapper around the gatecheck_core Rust extension module.

Centralizing the import here gives the Python side a single place to raise a
clear error if the wheel was installed without the native bits, and a single
place to mock during tests that don't need the runner.
"""

from __future__ import annotations

try:
    import gatecheck_core as _core
except ImportError as exc:  # pragma: no cover — only hit in broken installs
    raise ImportError(
        "gatecheck_core (the Rust extension) is not installed. "
        "Reinstall gatecheck from a wheel, or run `maturin develop` in gatecheck-rs/."
    ) from exc

core = _core

__all__ = ["core"]
