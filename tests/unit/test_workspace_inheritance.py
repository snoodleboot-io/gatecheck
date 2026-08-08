"""Unit tests for hooksmith.workspace.effective_config (STY-0017 / GAT-22).

Pure config layering; no I/O. Covers merge (id override in place, new appended, group
merge, sources fallback), override + none ignoring the root, and the per-package
inherit override of the workspace default. AAA structure throughout.
"""

from __future__ import annotations

from hooksmith.config import HooksmithConfig
from hooksmith.workspace import effective_config


def _cfg(
    hooks: list[str],
    *,
    inherit_ws: str | None = None,
    inherit_pkg: str | None = None,
    groups: dict[str, list[str]] | None = None,
    sources: dict[str, object] | None = None,
) -> HooksmithConfig:
    data: dict[str, object] = {
        "hook": [{"id": h, "from": "system", "run": h} for h in hooks],
    }
    if groups:
        data["group"] = {name: {"hooks": ids} for name, ids in groups.items()}
    if sources is not None:
        data["sources"] = sources
    if inherit_ws is not None:
        data["workspace"] = {"packages": ["x"], "inherit": inherit_ws}
    if inherit_pkg is not None:
        data["package"] = {"inherit": inherit_pkg}
    return HooksmithConfig.model_validate(data)


def _ids(config: HooksmithConfig) -> list[str]:
    return [h.id for h in config.hook]


def test_merge_overrides_hook_by_id_in_place() -> None:
    # Arrange — root a, b; package overrides b and adds c
    root = _cfg(["a", "b"], inherit_ws="merge")
    package = _cfg(["b", "c"])
    # Act
    effective = effective_config(root, package)
    # Assert — b kept its position, c appended; b is the package's version (run="b")
    assert _ids(effective) == ["a", "b", "c"]


def test_merge_merges_groups_by_name() -> None:
    # Arrange
    root = _cfg(["a"], inherit_ws="merge", groups={"lint": ["a"]})
    package = _cfg(["b"], groups={"test": ["b"]})
    # Act
    effective = effective_config(root, package)
    # Assert
    assert set(effective.group) == {"lint", "test"}


def test_merge_sources_fall_back_to_root() -> None:
    # Arrange — package has no sources; root does
    root = _cfg(["a"], inherit_ws="merge", sources={"default-registry": "https://root/simple"})
    package = _cfg(["b"])
    # Act
    effective = effective_config(root, package)
    # Assert
    assert effective.sources is not None
    assert effective.sources.default_registry == "https://root/simple"


def test_override_ignores_root() -> None:
    # Arrange
    root = _cfg(["a", "b"], inherit_ws="override")
    package = _cfg(["c"])
    # Act
    effective = effective_config(root, package)
    # Assert — only the package's hooks
    assert _ids(effective) == ["c"]


def test_none_ignores_root() -> None:
    # Arrange
    root = _cfg(["a"], inherit_ws="none")
    package = _cfg(["c"])
    # Act
    effective = effective_config(root, package)
    # Assert
    assert _ids(effective) == ["c"]


def test_package_inherit_overrides_workspace_default() -> None:
    # Arrange — workspace default is merge, but the package opts out with override
    root = _cfg(["a"], inherit_ws="merge")
    package = _cfg(["c"], inherit_pkg="override")
    # Act
    effective = effective_config(root, package)
    # Assert — override wins → root 'a' not inherited
    assert _ids(effective) == ["c"]
