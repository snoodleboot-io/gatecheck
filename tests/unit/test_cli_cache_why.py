"""Unit tests for `hooksmith cache why` (STY-0009 / GAT-11).

Hermetic via click's ``CliRunner`` in an isolated filesystem: a ``project`` hook
resolves against a fake ``.venv/bin/<tool>`` in the temp cwd (no PATH / network
dependency). Covers the human report, ``--json`` output, the unknown-hook error,
and a malformed-config error. AAA structure throughout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hooksmith.cli.main import main
from hooksmith.venv import bin_dir_name

_CONFIG = """
[[hook]]
id = "lint"
from = "project"
run = "mytool check"
"""


def _seed_workspace() -> None:
    """Write check.toml and a fake project venv executable into the cwd."""
    Path("check.toml").write_text(_CONFIG, encoding="utf-8")
    tool = Path(".venv") / bin_dir_name() / "mytool"
    tool.parent.mkdir(parents=True, exist_ok=True)
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)


@pytest.mark.integration
def test_cache_why_reports_key_and_status() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _seed_workspace()
        # Act
        result = runner.invoke(main, ["cache", "why", "lint"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "not-applicable" in result.output
        assert "cache key:" in result.output
        assert "mytool" in result.output


@pytest.mark.integration
def test_cache_why_json_round_trips() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _seed_workspace()
        # Act
        result = runner.invoke(main, ["cache", "why", "lint", "--json"])
        # Assert
        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload["hook_id"] == "lint"
        assert payload["source_kind"] == "project"
        assert payload["status"] == "not-applicable"


@pytest.mark.integration
def test_cache_why_unknown_hook_lists_available() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        _seed_workspace()
        # Act
        result = runner.invoke(main, ["cache", "why", "nope"])
        # Assert
        assert result.exit_code != 0
        assert "no hook with id 'nope'" in result.output
        assert "lint" in result.output  # lists available ids


@pytest.mark.integration
def test_cache_why_malformed_config_is_clean_error() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path("check.toml").write_text("this is not = valid = toml", encoding="utf-8")
        # Act
        result = runner.invoke(main, ["cache", "why", "lint"])
        # Assert — a clean ClickException, not a traceback
        assert result.exit_code != 0
        assert "check.toml" in result.output
        assert "Traceback" not in result.output
