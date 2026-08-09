"""Integration test for `hooksmith migrate` (STY-0020 / GAT-23).

End-to-end via ``CliRunner``: a fixture ``.pre-commit-config.yaml`` is migrated to a
``check.toml`` that loads back as a valid config, with warnings surfaced.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from hooksmith.cli.main import main
from hooksmith.config import load_config

pytestmark = pytest.mark.integration

_PRECOMMIT = """
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/acme/mystery
    hooks:
      - id: mystery
"""


def test_migrate_writes_a_loadable_check_toml() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        Path(".pre-commit-config.yaml").write_text(_PRECOMMIT, encoding="utf-8")
        # Act
        result = runner.invoke(main, ["migrate"])
        # Assert
        assert result.exit_code == 0, result.output
        assert "Wrote 3 hook(s) to check.toml" in result.output
        assert "warning:" in result.output  # the unknown 'mystery' repo warns
        # the emitted check.toml loads back as a valid config
        config = load_config(Path("check.toml"))
        assert [h.id for h in config.hook] == ["ruff", "ruff-format", "mystery"]
        assert config.hook[0].from_ == "pypi:ruff==0.4.0"


def test_migrate_missing_input_errors() -> None:
    # Arrange
    runner = CliRunner()
    with runner.isolated_filesystem():
        # Act — no .pre-commit-config.yaml present
        result = runner.invoke(main, ["migrate"])
        # Assert — click's exists=True guard rejects it
        assert result.exit_code != 0
