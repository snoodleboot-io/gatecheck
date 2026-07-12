"""Unit tests for the workspace schema + gatecheck.workspace.discover_workspace (STY-0016 / GAT-18).

Hermetic — real ``check.toml`` files under ``tmp_path``; no network. Covers the
`[workspace]`/`[package]` schema validation and package discovery (glob expansion,
skipping non-package dirs, dedupe, deterministic order, empty-when-no-workspace, and
a broken package config surfacing a ConfigError). AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

import pydantic
import pytest

from gatecheck.config import ConfigError, PackageSpec, WorkspaceSpec
from gatecheck.workspace import Workspace, discover_workspace

# ── schema ────────────────────────────────────────────────────────


def test_workspace_spec_defaults_inherit_merge() -> None:
    # Act
    spec = WorkspaceSpec.model_validate({"packages": ["packages/*"]})
    # Assert
    assert spec.packages == ["packages/*"]
    assert spec.inherit == "merge"


def test_workspace_spec_rejects_bad_inherit() -> None:
    with pytest.raises(pydantic.ValidationError):
        WorkspaceSpec.model_validate({"packages": ["x"], "inherit": "nope"})


def test_workspace_spec_rejects_empty_packages() -> None:
    with pytest.raises(pydantic.ValidationError):
        WorkspaceSpec.model_validate({"packages": []})


def test_package_spec_parses_depends_on_alias() -> None:
    # Act
    spec = PackageSpec.model_validate({"depends-on": ["shared"], "python": "3.11"})
    # Assert
    assert spec.depends_on == ["shared"]
    assert spec.python == "3.11"
    assert spec.inherit is None  # → workspace default


# ── discovery ─────────────────────────────────────────────────────


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _pkg_config(hook_id: str) -> str:
    return f'[[hook]]\nid = "{hook_id}"\nfrom = "system"\nrun = "{hook_id}"\n'


def test_discovers_packages_matching_globs(tmp_path: Path) -> None:
    # Arrange
    _write(tmp_path / "check.toml", '[workspace]\npackages = ["packages/*"]\n')
    _write(tmp_path / "packages" / "api" / "check.toml", _pkg_config("a"))
    _write(tmp_path / "packages" / "web" / "check.toml", _pkg_config("b"))
    # Act
    workspace = discover_workspace(tmp_path / "check.toml")
    # Assert
    assert isinstance(workspace, Workspace)
    assert [p.name for p in workspace.packages] == ["api", "web"]
    assert workspace.packages[0].config.hook[0].id == "a"


def test_skips_directories_without_check_toml(tmp_path: Path) -> None:
    # Arrange — packages/docs has no check.toml
    _write(tmp_path / "check.toml", '[workspace]\npackages = ["packages/*"]\n')
    _write(tmp_path / "packages" / "api" / "check.toml", _pkg_config("a"))
    (tmp_path / "packages" / "docs").mkdir(parents=True)
    # Act
    workspace = discover_workspace(tmp_path / "check.toml")
    # Assert
    assert [p.name for p in workspace.packages] == ["api"]


def test_dedupes_across_overlapping_globs(tmp_path: Path) -> None:
    # Arrange — two globs both match packages/api
    _write(tmp_path / "check.toml", '[workspace]\npackages = ["packages/*", "packages/api"]\n')
    _write(tmp_path / "packages" / "api" / "check.toml", _pkg_config("a"))
    # Act
    workspace = discover_workspace(tmp_path / "check.toml")
    # Assert
    assert len(workspace.packages) == 1


def test_no_workspace_table_yields_no_packages(tmp_path: Path) -> None:
    # Arrange — a plain single-package config
    _write(tmp_path / "check.toml", _pkg_config("a"))
    # Act
    workspace = discover_workspace(tmp_path / "check.toml")
    # Assert
    assert workspace.packages == ()
    assert workspace.root.hook[0].id == "a"


def test_broken_package_config_raises_config_error(tmp_path: Path) -> None:
    # Arrange — a package check.toml with an invalid hook (missing 'run')
    _write(tmp_path / "check.toml", '[workspace]\npackages = ["packages/*"]\n')
    _write(tmp_path / "packages" / "bad" / "check.toml", '[[hook]]\nid = "x"\nfrom = "system"\n')
    # Act / Assert
    with pytest.raises(ConfigError):
        discover_workspace(tmp_path / "check.toml")
