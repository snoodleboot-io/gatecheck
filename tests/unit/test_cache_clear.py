"""Unit tests for hooksmith.env.cache_clear (STY-0027 / GAT-29).

Hermetic — operates on a fake cache tree under ``tmp_path``. Covers slot removal
with count/bytes reporting, ``include_uv`` dropping the bootstrapped uv, ``dry_run``
leaving everything in place, and a missing cache yielding a zero outcome.
"""

from __future__ import annotations

from pathlib import Path

from hooksmith.env import ClearOutcome, clear_cache


def _make_slot(cache_root: Path, key: str, *, payload: bytes = b"x" * 1024) -> Path:
    """Create a fake venv slot under ``env-v1/<key>`` with one payload file."""
    slot = cache_root / "env-v1" / key / "bin"
    slot.mkdir(parents=True)
    (slot / "python").write_bytes(payload)
    return cache_root / "env-v1" / key


def test_removes_slots_and_reports_count_and_bytes(tmp_path: Path) -> None:
    # Arrange
    _make_slot(tmp_path, "aaa", payload=b"a" * 1024)
    _make_slot(tmp_path, "bbb", payload=b"b" * 2048)

    # Act
    outcome = clear_cache(tmp_path)

    # Assert
    assert outcome == ClearOutcome(removed=2, freed_bytes=3072)
    assert not (tmp_path / "env-v1" / "aaa").exists()
    assert not (tmp_path / "env-v1" / "bbb").exists()


def test_include_uv_removes_bootstrapped_uv(tmp_path: Path) -> None:
    # Arrange
    _make_slot(tmp_path, "aaa")
    uv_bin = tmp_path / "bin"
    uv_bin.mkdir()
    (uv_bin / "uv").write_bytes(b"u" * 512)

    # Act
    outcome = clear_cache(tmp_path, include_uv=True)

    # Assert — freed bytes include the uv payload; the uv dir is gone
    assert outcome.removed == 1
    assert outcome.freed_bytes == 1024 + 512
    assert not uv_bin.exists()


def test_uv_is_preserved_without_include_uv(tmp_path: Path) -> None:
    # Arrange
    _make_slot(tmp_path, "aaa")
    uv_bin = tmp_path / "bin"
    uv_bin.mkdir()
    (uv_bin / "uv").write_bytes(b"u" * 512)

    # Act
    outcome = clear_cache(tmp_path)

    # Assert — uv survives; its bytes are not counted
    assert outcome.freed_bytes == 1024
    assert uv_bin.exists()


def test_dry_run_deletes_nothing_but_reports(tmp_path: Path) -> None:
    # Arrange
    _make_slot(tmp_path, "aaa", payload=b"a" * 1024)

    # Act
    outcome = clear_cache(tmp_path, dry_run=True)

    # Assert — reported but untouched
    assert outcome == ClearOutcome(removed=1, freed_bytes=1024)
    assert (tmp_path / "env-v1" / "aaa").exists()


def test_missing_cache_is_zero_outcome(tmp_path: Path) -> None:
    # Act — nothing was ever created under tmp_path
    outcome = clear_cache(tmp_path / "nonexistent")

    # Assert
    assert outcome == ClearOutcome(removed=0, freed_bytes=0)


def test_empty_scheme_dir_is_zero_outcome(tmp_path: Path) -> None:
    # Arrange — the scheme dir exists but holds no slots
    (tmp_path / "env-v1").mkdir()

    # Act
    outcome = clear_cache(tmp_path)

    # Assert
    assert outcome == ClearOutcome(removed=0, freed_bytes=0)
    # the emptied scheme dir is tidied away
    assert not (tmp_path / "env-v1").exists()


def test_stray_file_in_scheme_dir_is_ignored(tmp_path: Path) -> None:
    # Arrange — a non-directory entry alongside no slots
    scheme = tmp_path / "env-v1"
    scheme.mkdir()
    (scheme / "README").write_text("not a slot")

    # Act
    outcome = clear_cache(tmp_path)

    # Assert — the stray file is neither counted nor removed
    assert outcome == ClearOutcome(removed=0, freed_bytes=0)
    assert (scheme / "README").exists()
