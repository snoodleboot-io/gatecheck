"""Opt-in integration test: a real uv-backed venv build (STY-0008 / GAT-10).

Marked ``integration`` + ``network`` and skipped when ``uv`` is not installed, so
the hermetic unit suite and offline CI never run it. Builds a real, small pinned
distribution (``pip``) into the cache and asserts the environment is usable and
reused on a second resolve.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvManager, ResolvedEnv

pytestmark = [pytest.mark.integration, pytest.mark.network]

_UV = shutil.which("uv")


@pytest.mark.skipif(_UV is None, reason="uv is not installed on this host")
def test_real_uv_build_and_reuse(tmp_path: Path) -> None:
    # Arrange — a pinned dist that ships a console script matching `run`.
    manager = EnvManager(cache_root=tmp_path)
    hook = HookDef.model_validate({"id": "smoke", "from": "pypi:pip==24.0", "run": "pip --version"})

    # Act
    first = manager.resolve(hook)
    second = manager.resolve(hook)

    # Assert — a real, reusable venv with the tool present.
    assert isinstance(first, ResolvedEnv)
    assert (first.bin_dir / "pip").exists()
    assert first == second  # same content-addressed slot on the second resolve
