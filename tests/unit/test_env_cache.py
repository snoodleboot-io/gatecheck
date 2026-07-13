"""Unit tests for gatecheck.env.env_cache (STY-0008 / GAT-10).

Pure filesystem — no subprocess, no network. Covers cache-root resolution, the
per-key venv slot, the health check, and the atomic temp-build-then-``os.replace``
publish (cache hit short-circuit, build-once, no partial slot on failure, and the
lost-publish-race branch). AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatecheck.env.env_cache import (
    default_cache_root,
    is_healthy,
    publish_atomically,
    venv_slot,
)
from gatecheck.venv import bin_dir_name


def _make_venv(dest: Path) -> None:
    """A minimal 'build': create the venv's ``bin`` dir so the slot reads healthy."""
    (dest / bin_dir_name()).mkdir(parents=True)


# ── default_cache_root ────────────────────────────────────────────


def test_default_cache_root_prefers_xdg(tmp_path: Path) -> None:
    # Arrange
    xdg = tmp_path / "xdg"
    # Act
    root = default_cache_root({"XDG_CACHE_HOME": str(xdg)})
    # Assert
    assert root == xdg / "gatecheck"


def test_default_cache_root_falls_back_to_home_cache(tmp_path: Path) -> None:
    # Arrange
    home = tmp_path / "home"
    # Act
    root = default_cache_root({"HOME": str(home)})
    # Assert
    assert root == home / ".cache" / "gatecheck"


# ── venv_slot / is_healthy ────────────────────────────────────────


def test_venv_slot_is_scheme_namespaced(tmp_path: Path) -> None:
    # Act
    slot = venv_slot(tmp_path, "abc123")
    # Assert
    assert slot == tmp_path / "env-v1" / "abc123"


def test_is_healthy_true_only_when_bin_present(tmp_path: Path) -> None:
    # Arrange
    slot = tmp_path / "env-v1" / "k"
    slot.mkdir(parents=True)
    # Assert — no bin yet
    assert is_healthy(slot) is False
    # Arrange — add bin
    (slot / bin_dir_name()).mkdir()
    # Assert
    assert is_healthy(slot) is True


# ── publish_atomically ────────────────────────────────────────────


def test_publish_builds_on_miss_and_returns_healthy_slot(tmp_path: Path) -> None:
    # Arrange
    calls: list[Path] = []

    def build(dest: Path) -> None:
        calls.append(dest)
        _make_venv(dest)

    # Act
    slot = publish_atomically(build, tmp_path, "key1")
    # Assert
    assert slot == venv_slot(tmp_path, "key1")
    assert is_healthy(slot)
    assert len(calls) == 1


def test_publish_is_a_cache_hit_when_slot_already_healthy(tmp_path: Path) -> None:
    # Arrange — pre-populate a healthy slot
    slot = venv_slot(tmp_path, "key2")
    (slot / bin_dir_name()).mkdir(parents=True)
    built = False

    def build(dest: Path) -> None:
        nonlocal built
        built = True
        _make_venv(dest)

    # Act
    result = publish_atomically(build, tmp_path, "key2")
    # Assert — build was NOT called
    assert result == slot
    assert built is False


def test_publish_leaves_no_partial_slot_when_build_fails(tmp_path: Path) -> None:
    # Arrange
    def build(dest: Path) -> None:
        (dest / bin_dir_name()).mkdir()  # partial work that must be discarded
        raise RuntimeError("boom")

    # Act / Assert
    with pytest.raises(RuntimeError, match="boom"):
        publish_atomically(build, tmp_path, "key3")
    assert not venv_slot(tmp_path, "key3").exists()
    # No leftover .building-* temp dirs.
    assert list((tmp_path / "env-v1").glob(".building-*")) == []


def test_publish_discards_temp_when_slot_won_by_a_peer(tmp_path: Path) -> None:
    # Arrange — the build both populates its temp AND simulates a peer publishing
    # the final slot first, so os.replace onto the non-empty slot raises OSError.
    slot = venv_slot(tmp_path, "key4")

    def build(dest: Path) -> None:
        _make_venv(dest)
        (slot / bin_dir_name()).mkdir(parents=True)  # peer wins the race

    # Act
    result = publish_atomically(build, tmp_path, "key4")
    # Assert — returns the peer's healthy slot, discards our temp
    assert result == slot
    assert is_healthy(slot)
    assert list((tmp_path / "env-v1").glob(".building-*")) == []
