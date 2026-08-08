"""Unit tests for hooksmith.migration.parse_precommit_config (STY-0019 / GAT-19).

Hermetic — real YAML fixtures written under ``tmp_path``. Covers a valid config
(repos + hook fields), empty file, and the ``MigrationError``s for malformed YAML,
a non-mapping top level, and schema failures. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hooksmith.migration import MigrationError, PreCommitConfig, parse_precommit_config

_VALID = """
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: ["--fix"]
      - id: ruff-format
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
        language: python
        files: '\\.py$'
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / ".pre-commit-config.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_parses_repos_and_hooks(tmp_path: Path) -> None:
    # Act
    config = parse_precommit_config(_write(tmp_path, _VALID))
    # Assert
    assert isinstance(config, PreCommitConfig)
    assert [r.repo.rsplit("/", 1)[-1] for r in config.repos] == ["ruff-pre-commit", "black"]
    ruff_repo = config.repos[0]
    assert ruff_repo.rev == "v0.4.0"
    assert [h.id for h in ruff_repo.hooks] == ["ruff", "ruff-format"]
    assert ruff_repo.hooks[0].args == ["--fix"]
    assert config.repos[1].hooks[0].files == r"\.py$"


def test_empty_file_yields_no_repos(tmp_path: Path) -> None:
    # Act
    config = parse_precommit_config(_write(tmp_path, ""))
    # Assert
    assert config.repos == []


def test_extra_keys_are_ignored(tmp_path: Path) -> None:
    # Arrange — pre-commit configs carry many keys we don't model
    body = "default_language_version:\n  python: python3.11\nrepos: []\n"
    # Act
    config = parse_precommit_config(_write(tmp_path, body))
    # Assert
    assert config.repos == []


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="invalid YAML"):
        parse_precommit_config(_write(tmp_path, "repos: [unbalanced\n"))


def test_non_mapping_top_level_raises(tmp_path: Path) -> None:
    with pytest.raises(MigrationError, match="mapping at the top level"):
        parse_precommit_config(_write(tmp_path, "- just\n- a\n- list\n"))


def test_missing_repo_field_raises(tmp_path: Path) -> None:
    # Arrange — a repo entry without the required 'repo'
    body = "repos:\n  - rev: v1\n    hooks:\n      - id: x\n"
    with pytest.raises(MigrationError):
        parse_precommit_config(_write(tmp_path, body))


def test_missing_hook_id_raises(tmp_path: Path) -> None:
    body = "repos:\n  - repo: r\n    hooks:\n      - name: no-id\n"
    with pytest.raises(MigrationError):
        parse_precommit_config(_write(tmp_path, body))
