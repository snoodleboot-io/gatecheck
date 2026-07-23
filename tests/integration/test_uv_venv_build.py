"""Opt-in integration tests: real uv-backed venv builds (STY-0008 / GAT-10, BUG-0001).

Marked ``integration`` + ``network`` and skipped when ``uv`` is not installed, so
the hermetic unit suite and offline CI never run it. Builds real pinned
distributions into the cache and asserts the environment is usable and reused.

Three shapes are covered deliberately:

* ``pip`` — a pure-Python distribution shipping a **single** universal wheel.
* ``ruff`` — a compiled tool shipping **one wheel per platform**.
* ``detect-secrets`` — a tool **with dependencies** (pyyaml, requests, …). This is the
  shape that BUG-0006 broke: installing with ``--require-hashes`` demanded every
  transitive dependency also be pinned+hashed, which gatecheck can't provide, so any
  package with deps failed. ``ruff`` and ``pip`` have no deps, so they alone could
  never catch it — which is exactly why it shipped unnoticed.
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


@pytest.mark.skipif(_UV is None, reason="uv is not installed on this host")
def test_real_uv_build_of_multi_wheel_distribution(tmp_path: Path) -> None:
    """A distribution with per-platform wheels must install (ruff ships one per OS/arch)."""
    # Arrange
    manager = EnvManager(cache_root=tmp_path)
    hook = HookDef.model_validate(
        {"id": "lint", "from": "pypi:ruff==0.4.0", "run": "ruff --version"}
    )

    # Act
    resolved = manager.resolve(hook)

    # Assert — the platform-correct wheel installed and the tool is present
    assert isinstance(resolved, ResolvedEnv)
    assert any((resolved.bin_dir / name).exists() for name in ("ruff", "ruff.exe"))


@pytest.mark.skipif(_UV is None, reason="uv is not installed on this host")
def test_real_uv_build_of_distribution_with_dependencies(tmp_path: Path) -> None:
    """BUG-0006 regression: a package WITH dependencies must install.

    detect-secrets pulls in pyyaml/requests/urllib3. Under the old ``--require-hashes``
    install this failed — 'all requirements must be pinned upfront with ==, but found:
    pyyaml' — because only the top-level hash was known. Installing by exact version and
    letting uv resolve the tree fixes it.
    """
    # Arrange
    manager = EnvManager(cache_root=tmp_path)
    hook = HookDef.model_validate(
        {"id": "secrets", "from": "pypi:detect-secrets==1.5.0", "run": "detect-secrets --version"}
    )

    # Act
    resolved = manager.resolve(hook)

    # Assert — the tool installed alongside its dependencies
    assert isinstance(resolved, ResolvedEnv)
    assert any((resolved.bin_dir / name).exists() for name in ("detect-secrets", "detect-secrets.exe"))
