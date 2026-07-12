"""Shared pytest fixtures + collection markers."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent / "fixtures"

# Test modules whose fakes assume the POSIX venv layout (bin/, extensionless
# executables, bin/uv). They pass on POSIX; the Windows CI lane deselects them
# (-m "not posix_only") until they are made cross-platform (GAT-38).
_POSIX_ONLY_MODULES = frozenset(
    {
        "test_env_cache",
        "test_env_manager",
        "test_env_manager_pypi",
        "test_uv_runner",
        "test_uv_bootstrap",
        "test_cache_explain",
        "test_source_resolve",
    }
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Tag POSIX-coupled modules with the ``posix_only`` marker."""
    for item in items:
        if item.path.stem in _POSIX_ONLY_MODULES:
            item.add_marker(pytest.mark.posix_only)


@pytest.fixture
def sample_check_toml() -> Path:
    """Path to the bundled sample check.toml."""
    return FIXTURE_DIR / "check.toml.sample"
