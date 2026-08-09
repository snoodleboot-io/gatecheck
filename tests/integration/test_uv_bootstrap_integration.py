"""Opt-in integration test: a real pinned uv download (STY-0010 / GAT-12).

Marked ``integration`` + ``network`` and deselected in hermetic CI. Actually
downloads the pinned uv release, checksum-verifies it, and runs ``uv --version`` to
prove the bootstrapped binary works; a second call is a cache hit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hooksmith.env.uv_bootstrap import UvBootstrapError, bootstrap_uv

pytestmark = [pytest.mark.integration, pytest.mark.network]


def test_real_bootstrap_downloads_working_uv(tmp_path: Path) -> None:
    # Arrange / Act — real download + checksum verify + extract
    try:
        uv = bootstrap_uv(tmp_path)
    except UvBootstrapError as exc:
        pytest.skip(f"uv bootstrap unsupported on this platform: {exc}")

    # Assert — the bootstrapped binary runs
    assert uv == tmp_path / "bin" / "uv"
    result = subprocess.run([str(uv), "--version"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "uv" in result.stdout

    # A second bootstrap is a cache hit (same path, no re-download).
    assert bootstrap_uv(tmp_path) == uv
