"""End-to-end CLI smoke test using click's CliRunner."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from gatecheck.cli.main import main


@pytest.mark.integration
def test_help_lists_all_subcommands() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for name in ("install", "sync", "run", "cache", "migrate"):
        assert name in result.output


@pytest.mark.integration
def test_version_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "gatecheck" in result.output
