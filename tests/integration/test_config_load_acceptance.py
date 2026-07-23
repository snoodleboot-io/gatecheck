"""Acceptance tests for STY-0001 — Load check.toml into a validated model.

These integration tests mirror the four acceptance criteria from
``planning/features/FEAT-0001-config-loader/stories/STY-0001-load-check-toml.md``
verbatim, plus a public-import smoke test that locks down the
five-symbol facade declared in the BUILD-0001 architecture sketch
(``planning/build-plans/0001-architecture-sketch.md``).

Lane B (this file) writes the tests in the RED state. Lane D will
implement ``gatecheck.config`` to make them green. Do not mock the
loader or any pydantic model — the contract is asserted against real
artifacts (the repo's own ``check.toml``, the real ``mypy`` and
``pytest`` binaries in the active venv).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from gatecheck.config import (
    GatecheckConfig,
    GroupDef,
    HookDef,
    SourceSpec,
    load_config,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[2]


def test_load_repo_check_toml_returns_non_empty_config() -> None:
    """Given the repo's own check.toml,
    When load_config is invoked on it,
    Then it returns a populated GatecheckConfig matching the file's contents.

    Covers STY-0001 acceptance criterion 2.
    """
    # Arrange
    check_toml_path: Path = REPO_ROOT / "check.toml"

    # Act
    cfg: GatecheckConfig = load_config(check_toml_path)

    # Assert — structural, not pinned to exact hook count or ruff version, so this
    # doesn't fail every time the repo's own config is tuned.
    assert isinstance(cfg, GatecheckConfig)
    assert len(cfg.hook) >= 1
    assert len(cfg.group) >= 3
    assert cfg.hook[0].id == "ruff"
    assert cfg.hook[0].from_.startswith("pypi:ruff")
    assert cfg.group["lint"].parallel is True


@pytest.mark.integration
@pytest.mark.slow
def test_mypy_strict_passes_on_config_package() -> None:
    """Given the gatecheck.config package and the project's strict mypy settings,
    When mypy --strict is run against src/gatecheck/config/,
    Then it exits cleanly with no errors on stderr.

    Covers STY-0001 acceptance criterion 3.
    """
    # Arrange
    mypy_bin: Path = Path(sys.executable).parent / "mypy"

    # Act
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [str(mypy_bin), "--strict", "src/gatecheck/config/"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0, (
        f"mypy --strict failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert result.stderr == ""


def test_config_package_public_imports() -> None:
    """Given the gatecheck.config public facade,
    When the five documented symbols are imported,
    Then each resolves to a non-None object of the expected kind.

    Locks the BUILD-0001 architecture sketch §2 public API surface.
    """
    # Arrange / Act
    # Imports happen at module load time; re-bind here for explicit assertion.
    symbols: dict[str, object] = {
        "load_config": load_config,
        "GatecheckConfig": GatecheckConfig,
        "HookDef": HookDef,
        "SourceSpec": SourceSpec,
        "GroupDef": GroupDef,
    }

    # Assert
    for name, obj in symbols.items():
        assert obj is not None, f"{name} should not be None"
    assert callable(load_config)
    assert isinstance(GatecheckConfig, type)
    assert isinstance(HookDef, type)
    assert isinstance(SourceSpec, type)
    assert isinstance(GroupDef, type)


def test_no_runtime_dependency_on_gatecheck_core() -> None:
    """Given a fresh Python subprocess,
    When every module of gatecheck.config is imported,
    Then gatecheck_core is not pulled into sys.modules as a side effect.

    Covers STY-0001 acceptance criterion 4 — no new runtime dependency
    beyond pydantic>=2. The Rust core wheel must never be imported by
    pure-Python config loading.
    """
    # Arrange
    probe: str = (
        "import sys; "
        "import gatecheck.config; "
        "import gatecheck.config.loader; "
        "import gatecheck.config.gatecheck_config; "
        "import gatecheck.config.hook_def; "
        "import gatecheck.config.group_def; "
        "import gatecheck.config.source_spec; "
        "assert 'gatecheck_core' not in sys.modules, sorted(sys.modules)"
    )

    # Act
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0, (
        f"gatecheck.config imports leaked gatecheck_core.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX-only tests skip on Windows, lowering measured coverage; Linux enforces the gate",
)
def test_unit_test_coverage_meets_ninety_percent() -> None:
    """Given the unit tests for the config package,
    When pytest is run with --cov-fail-under=90 against gatecheck.config,
    Then it exits with code 0, proving coverage meets the threshold.

    Covers STY-0001 acceptance criterion 1.
    """
    # Arrange
    pytest_bin: Path = Path(sys.executable).parent / "pytest"

    # Act
    result: subprocess.CompletedProcess[str] = subprocess.run(
        [
            str(pytest_bin),
            "tests/unit/test_config_loader.py",
            "tests/unit/test_config_schema.py",
            # STY-0002: ConfigError + _error_translator live alongside the loader and
            # share the same coverage gate. Include their unit tests in the gate.
            "tests/unit/test_config_error.py",
            "--cov=gatecheck.config",
            "--cov-report=term",
            "--cov-fail-under=90",
            "-q",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    # Assert
    assert result.returncode == 0, (
        f"unit-test coverage gate failed.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
