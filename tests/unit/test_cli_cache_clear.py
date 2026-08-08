"""Unit tests for `hooksmith cache clear` (STY-0027 / GAT-29).

Hermetic via click's ``CliRunner``: ``XDG_CACHE_HOME`` points at a temp tree so the
command clears a fake cache with no real environments. Covers the human summary,
``--all`` (uv removal), ``--dry-run`` (preview), and an empty cache.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from hooksmith.cli.main import main


def _seed_cache(cache_home: Path, *, keys: tuple[str, ...] = ("aaa",)) -> Path:
    """Create fake venv slots under ``<cache_home>/hooksmith/env-v1`` and return the root."""
    root = cache_home / "hooksmith"
    for key in keys:
        slot = root / "env-v1" / key / "bin"
        slot.mkdir(parents=True)
        (slot / "python").write_bytes(b"x" * 1024)
    return root


def test_clear_reports_removed_environments(tmp_path: Path) -> None:
    # Arrange
    _seed_cache(tmp_path, keys=("aaa", "bbb"))
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cache", "clear"], env={"XDG_CACHE_HOME": str(tmp_path)})
    # Assert
    assert result.exit_code == 0, result.output
    assert "Removed 2 cached environments" in result.output
    assert not (tmp_path / "hooksmith" / "env-v1" / "aaa").exists()


def test_clear_singular_grammar(tmp_path: Path) -> None:
    # Arrange
    _seed_cache(tmp_path, keys=("aaa",))
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cache", "clear"], env={"XDG_CACHE_HOME": str(tmp_path)})
    # Assert
    assert result.exit_code == 0, result.output
    assert "Removed 1 cached environment," in result.output


def test_clear_all_removes_bootstrapped_uv(tmp_path: Path) -> None:
    # Arrange
    root = _seed_cache(tmp_path)
    uv_bin = root / "bin"
    uv_bin.mkdir()
    (uv_bin / "uv").write_bytes(b"u" * 512)
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cache", "clear", "--all"], env={"XDG_CACHE_HOME": str(tmp_path)})
    # Assert
    assert result.exit_code == 0, result.output
    assert not uv_bin.exists()


def test_dry_run_previews_without_deleting(tmp_path: Path) -> None:
    # Arrange
    _seed_cache(tmp_path)
    runner = CliRunner()
    # Act
    result = runner.invoke(
        main, ["cache", "clear", "--dry-run"], env={"XDG_CACHE_HOME": str(tmp_path)}
    )
    # Assert
    assert result.exit_code == 0, result.output
    assert "Would remove 1 cached environment," in result.output
    assert (tmp_path / "hooksmith" / "env-v1" / "aaa").exists()


def test_empty_cache_reports_zero(tmp_path: Path) -> None:
    # Arrange — no cache seeded
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cache", "clear"], env={"XDG_CACHE_HOME": str(tmp_path)})
    # Assert
    assert result.exit_code == 0, result.output
    assert "Removed 0 cached environments, freeing 0 B." in result.output


@pytest.mark.parametrize(
    ("payload_kib", "expected"),
    [(1, "1.0 KiB"), (1536, "1.5 MiB")],
)
def test_human_bytes_rendering(tmp_path: Path, payload_kib: int, expected: str) -> None:
    # Arrange — one slot whose payload rounds to the expected human size
    root = tmp_path / "hooksmith"
    slot = root / "env-v1" / "aaa" / "bin"
    slot.mkdir(parents=True)
    (slot / "python").write_bytes(b"x" * (payload_kib * 1024))
    runner = CliRunner()
    # Act
    result = runner.invoke(main, ["cache", "clear"], env={"XDG_CACHE_HOME": str(tmp_path)})
    # Assert
    assert result.exit_code == 0, result.output
    assert f"freeing {expected}." in result.output
