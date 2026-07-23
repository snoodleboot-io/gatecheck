"""Unit tests for gatecheck.config.discover_config (GAT-48).

Hermetic — real directory trees under ``tmp_path``; no CWD dependence (``start`` is
passed explicitly). Covers finding a ``check.toml`` in the start dir and in a parent,
the ``pyproject.toml`` fallback (only when it carries ``[tool.gatecheck]``), the
check.toml-wins precedence, stopping at the repo root, and the not-found result.
"""

from __future__ import annotations

from pathlib import Path

from gatecheck.config import discover_config

_HOOK = '[[hook]]\nid = "a"\nfrom = "system"\nrun = "echo"\n'
_PYPROJECT = '[tool.gatecheck]\n[[tool.gatecheck.hook]]\nid = "a"\nfrom = "system"\nrun = "echo"\n'


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_finds_check_toml_in_start_dir(tmp_path: Path) -> None:
    # Arrange
    cfg = _write(tmp_path / "check.toml", _HOOK)
    # Act / Assert
    assert discover_config(tmp_path) == cfg


def test_walks_up_to_a_parent(tmp_path: Path) -> None:
    # Arrange — config at the root, search from a deep subdir
    cfg = _write(tmp_path / "check.toml", _HOOK)
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    # Act / Assert
    assert discover_config(deep) == cfg


def test_pyproject_fallback_when_it_has_the_table(tmp_path: Path) -> None:
    # Arrange — only a pyproject.toml, carrying [tool.gatecheck]
    cfg = _write(tmp_path / "pyproject.toml", _PYPROJECT)
    # Act / Assert
    assert discover_config(tmp_path) == cfg


def test_pyproject_without_the_table_is_ignored(tmp_path: Path) -> None:
    # Arrange — a pyproject.toml with no [tool.gatecheck]
    _write(tmp_path / "pyproject.toml", '[tool.poetry]\nname = "x"\n')
    # Act / Assert — not a gatecheck config, nothing else present
    assert discover_config(tmp_path) is None


def test_check_toml_wins_over_pyproject(tmp_path: Path) -> None:
    # Arrange — both present in the same dir
    cfg = _write(tmp_path / "check.toml", _HOOK)
    _write(tmp_path / "pyproject.toml", _PYPROJECT)
    # Act / Assert
    assert discover_config(tmp_path) == cfg


def test_stops_at_the_repo_root(tmp_path: Path) -> None:
    # Arrange — config ABOVE a .git boundary must not be found from inside the repo
    _write(tmp_path / "check.toml", _HOOK)  # "outside" the repo
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "pkg"
    sub.mkdir()
    # Act — searching from repo/pkg stops after repo (the .git dir), never reaching tmp_path
    assert discover_config(sub) is None


def test_finds_config_at_the_repo_root(tmp_path: Path) -> None:
    # Arrange — the repo root itself has the config and the .git marker
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    cfg = _write(repo / "check.toml", _HOOK)
    sub = repo / "pkg" / "deep"
    sub.mkdir(parents=True)
    # Act / Assert — found at the root, which is where the walk stops
    assert discover_config(sub) == cfg


def test_returns_none_when_nothing_is_found(tmp_path: Path) -> None:
    # Arrange — an empty tree
    empty = tmp_path / "empty"
    empty.mkdir()
    # Act / Assert
    assert discover_config(empty) is None


def test_malformed_pyproject_is_skipped_not_raised(tmp_path: Path) -> None:
    # Arrange — a pyproject.toml that doesn't parse
    _write(tmp_path / "pyproject.toml", "this is = = not toml")
    # Act / Assert — discovery treats it as "not a config" and returns None
    assert discover_config(tmp_path) is None
