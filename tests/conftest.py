"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_check_toml() -> Path:
    """Path to the bundled sample check.toml."""
    return FIXTURE_DIR / "check.toml.sample"
