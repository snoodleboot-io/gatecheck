"""Unit tests for hooksmith.workspace.affected_packages (STY-0018 / GAT-24).

Hermetic — real monorepo layouts under ``tmp_path`` (no git; changed files passed
directly). Covers directly-changed detection, transitive dependent propagation,
ordering, and the unknown-dependency / cycle ``WorkspaceError``s. AAA throughout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from hooksmith.workspace import WorkspaceError, affected_packages, discover_workspace, run_affected


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _package(tmp_path: Path, name: str, depends_on: list[str] | None = None) -> None:
    body = '[[hook]]\nid = "lint"\nfrom = "system"\nrun = "echo"\npass-files = false\n'
    if depends_on:
        deps = ", ".join(f'"{d}"' for d in depends_on)
        body += f"\n[package]\ndepends-on = [{deps}]\n"
    _write(tmp_path / "packages" / name / "check.toml", body)


def _workspace(tmp_path: Path):
    _write(tmp_path / "check.toml", '[workspace]\npackages = ["packages/*"]\n')
    return discover_workspace(tmp_path / "check.toml")


def _names(packages: tuple[object, ...]) -> list[str]:
    return [p.name for p in packages]  # type: ignore[attr-defined]


def test_directly_changed_package_is_affected(tmp_path: Path) -> None:
    # Arrange
    _package(tmp_path, "a")
    _package(tmp_path, "b")
    workspace = _workspace(tmp_path)
    # Act — a file under packages/a changed
    affected = affected_packages(workspace, [Path("packages/a/x.py")])
    # Assert
    assert _names(affected) == ["a"]


def test_dependents_are_affected_transitively(tmp_path: Path) -> None:
    # Arrange — c -> b -> a (c depends on b, b depends on a)
    _package(tmp_path, "a")
    _package(tmp_path, "b", depends_on=["a"])
    _package(tmp_path, "c", depends_on=["b"])
    workspace = _workspace(tmp_path)
    # Act — a changed → a, b, c all affected
    affected = affected_packages(workspace, [Path("packages/a/x.py")])
    # Assert — workspace-declared order
    assert _names(affected) == ["a", "b", "c"]


def test_unrelated_package_is_not_affected(tmp_path: Path) -> None:
    # Arrange
    _package(tmp_path, "a")
    _package(tmp_path, "b", depends_on=["a"])
    _package(tmp_path, "d")  # unrelated
    workspace = _workspace(tmp_path)
    # Act — change b only
    affected = affected_packages(workspace, [Path("packages/b/y.py")])
    # Assert — b changed; d unrelated; a is a dependency of b (not a dependent) → not affected
    assert _names(affected) == ["b"]


def test_unknown_dependency_raises(tmp_path: Path) -> None:
    # Arrange — a depends on a package that does not exist
    _package(tmp_path, "a", depends_on=["ghost"])
    workspace = _workspace(tmp_path)
    # Act / Assert
    with pytest.raises(WorkspaceError, match="unknown package 'ghost'"):
        affected_packages(workspace, [Path("packages/a/x.py")])


def test_dependency_cycle_raises(tmp_path: Path) -> None:
    # Arrange — a <-> b
    _package(tmp_path, "a", depends_on=["b"])
    _package(tmp_path, "b", depends_on=["a"])
    workspace = _workspace(tmp_path)
    # Act / Assert
    with pytest.raises(WorkspaceError, match="cycle"):
        affected_packages(workspace, [Path("packages/a/x.py")])


def test_empty_changeset_affects_nothing(tmp_path: Path) -> None:
    # Arrange
    _package(tmp_path, "a")
    workspace = _workspace(tmp_path)
    # Act — genuinely no changed files
    affected = affected_packages(workspace, [])
    # Assert
    assert affected == ()


def test_root_change_affects_all_packages(tmp_path: Path) -> None:
    # Arrange — three unrelated packages
    _package(tmp_path, "a")
    _package(tmp_path, "b")
    _package(tmp_path, "c")
    workspace = _workspace(tmp_path)
    # Act — a shared/root file (under no package) changed
    affected = affected_packages(workspace, [Path("check.toml")])
    # Assert — every package, in declared order
    assert _names(affected) == ["a", "b", "c"]


def test_root_change_mixed_with_package_change_still_all(tmp_path: Path) -> None:
    # Arrange
    _package(tmp_path, "a")
    _package(tmp_path, "b")
    workspace = _workspace(tmp_path)
    # Act — a package file AND a root lockfile changed
    affected = affected_packages(workspace, [Path("packages/a/x.py"), Path("uv.lock")])
    # Assert — root change dominates → all packages
    assert _names(affected) == ["a", "b"]


# ── [package].python threads into the env manager (GAT-47) ─────────


def test_run_affected_passes_package_python_to_env_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A package's [package].python must reach the EnvManager that builds its venvs."""
    # Arrange — one package pinning python 3.9, with a system hook (no real venv build)
    body = (
        '[[hook]]\nid = "lint"\nfrom = "system"\nrun = "echo"\npass-files = false\n'
        '\n[package]\npython = "3.9"\n'
    )
    _write(tmp_path / "packages" / "api" / "check.toml", body)
    workspace = _workspace(tmp_path)

    # Spy on the EnvManager the affected runner constructs.
    captured: dict[str, object] = {}
    import hooksmith.workspace.affected as affected_mod

    real_env_manager = affected_mod.EnvManager

    def spy(*args: object, **kwargs: object) -> object:
        captured["python_version"] = kwargs.get("python_version")
        return real_env_manager(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(affected_mod, "EnvManager", spy)

    # Act — a change under the package
    run_affected(workspace, [Path("packages/api/x.py")])

    # Assert
    assert captured["python_version"] == "3.9"


def test_run_affected_python_version_none_when_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — a package with no [package].python
    _package(tmp_path, "api")
    workspace = _workspace(tmp_path)
    captured: dict[str, object] = {}
    import hooksmith.workspace.affected as affected_mod

    real = affected_mod.EnvManager
    monkeypatch.setattr(
        affected_mod,
        "EnvManager",
        lambda *a, **k: (
            captured.__setitem__("python_version", k.get("python_version")),
            real(*a, **k),
        )[1],
    )
    # Act
    run_affected(workspace, [Path("packages/api/x.py")])
    # Assert
    assert captured["python_version"] is None
