"""Unit tests for the release version calculator (STY-0044 / GAT-53).

The script lives at ``.github/scripts/calculate_version.py`` — outside the importable
package — so it is loaded by path. PyPI lookups are stubbed; no network. AAA structure.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "calculate_version.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("calculate_version", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


calc = _load()


def _calculator(pypi: tuple[int, int] | None) -> object:
    """A VersionCalculator whose PyPI lookup returns a fixed (major, minor) or None."""
    return calc.VersionCalculator(package_name="gatecheck", pypi_lookup=lambda _name: pypi)


# ── MINOR derivation ──────────────────────────────────────────────


def test_first_release_starts_at_minor_one() -> None:
    # Arrange — nothing published yet
    calculator = _calculator(None)
    # Act — a push to main is the release path
    version = calculator.calculate_version(
        major=0,
        pr_number=None,
        run_number=None,
        is_testpypi=False,
        is_pr=False,
        github_ref="refs/heads/main",
    )
    # Assert — debut version is 0.1.0, not 0.0.0
    assert version == "0.1.0"


def test_minor_is_pypi_latest_plus_one_for_same_major() -> None:
    # Arrange — PyPI already has 0.3
    calculator = _calculator((0, 3))
    # Act
    version = calculator.calculate_version(
        major=0,
        pr_number=None,
        run_number=None,
        is_testpypi=False,
        is_pr=False,
        github_ref="refs/heads/main",
    )
    # Assert
    assert version == "0.4.0"


def test_major_bump_restarts_minor_at_one() -> None:
    # Arrange — latest on PyPI is 0.7, but we now build MAJOR 1
    calculator = _calculator((0, 7))
    # Act
    version = calculator.calculate_version(
        major=1,
        pr_number=None,
        run_number=None,
        is_testpypi=False,
        is_pr=False,
        github_ref="refs/heads/main",
    )
    # Assert
    assert version == "1.1.0"


# ── PATCH / PR context ────────────────────────────────────────────


def test_pr_build_uses_pr_number_as_patch_with_dev_run() -> None:
    # Arrange — a TestPyPI preview from PR #42, run 99
    calculator = _calculator((0, 2))
    # Act
    version = calculator.calculate_version(
        major=0,
        pr_number="42",
        run_number="99",
        is_testpypi=True,
        is_pr=True,
        github_ref="refs/pull/42/merge",
    )
    # Assert — 0.<minor>.<pr>-dev<run>: valid SemVer for Cargo, == PEP 440 0.3.42.dev99
    assert version == "0.3.42-dev99"


def test_push_to_main_is_a_clean_release_version() -> None:
    # Arrange
    calculator = _calculator((0, 1))
    # Act
    version = calculator.calculate_version(
        major=0,
        pr_number=None,
        run_number="7",
        is_testpypi=False,
        is_pr=False,
        github_ref="refs/heads/main",
    )
    # Assert — no dev suffix, PATCH 0
    assert version == "0.2.0"


def test_feature_branch_push_is_a_throwaway_dev_build() -> None:
    # Arrange
    calculator = _calculator(None)
    # Act
    version = calculator.calculate_version(
        major=0,
        pr_number=None,
        run_number=None,
        is_testpypi=False,
        is_pr=False,
        github_ref="refs/heads/feat/x",
    )
    # Assert — hyphen form (SemVer-valid); never published anyway
    assert version == "0.1.0-dev0"


def test_pr_build_without_a_pr_number_is_fatal() -> None:
    # Arrange — a PR event that somehow carries no PR number
    calculator = _calculator((0, 1))
    # Act / Assert
    with pytest.raises(SystemExit):
        calculator.calculate_version(
            major=0,
            pr_number=None,
            run_number=None,
            is_testpypi=True,
            is_pr=True,
            github_ref="refs/pull//merge",
        )


def test_preview_version_is_valid_in_both_ecosystems() -> None:
    """The preview version must parse as PEP 440 (Python wheels) and as SemVer (Cargo).

    Guards the '-dev' hyphen form: a '.dev' dot is a Cargo parse error, and a bare
    SemVer '-dev' still normalizes to PEP 440 '.dev'.
    """
    # Arrange
    from packaging.version import Version

    calculator = _calculator((0, 2))
    # Act
    version = calculator.calculate_version(
        major=0,
        pr_number="42",
        run_number="99",
        is_testpypi=True,
        is_pr=True,
        github_ref="refs/pull/42/merge",
    )
    # Assert — PEP 440 normalization collapses the hyphen to the dot form...
    assert str(Version(version)) == "0.3.42.dev99"
    # ...and it is valid SemVer: MAJOR.MINOR.PATCH with a hyphen-delimited prerelease.
    assert re.fullmatch(r"\d+\.\d+\.\d+-[0-9A-Za-z.]+", version)


# ── PR-number extraction ──────────────────────────────────────────


def test_pr_number_extracted_from_pull_ref() -> None:
    assert calc._extract_pr_number("refs/pull/128/merge") == "128"


def test_pr_number_absent_from_branch_ref() -> None:
    assert calc._extract_pr_number("refs/heads/main") is None
