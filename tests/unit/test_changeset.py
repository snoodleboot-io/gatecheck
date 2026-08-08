"""Unit tests for hooksmith.runner.resolve_changeset (STY-0011 / GAT-13).

Hermetic — the git boundary is a dependency-injected ``FakeGitClient``; no real
repository. Covers staged (default) vs ``all_files``, the ``files`` glob filter,
``pass_files=False``, ``files=None`` (all files), subdir path matching, and the
per-hook mapping across multiple hooks. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

from hooksmith.config.hook_def import HookDef
from hooksmith.runner import Changeset, resolve_changeset


class FakeGitClient:
    """In-memory GitClient returning canned staged / tracked / changed-since lists."""

    def __init__(
        self,
        staged: list[str] | None = None,
        tracked: list[str] | None = None,
        changed: list[str] | None = None,
    ) -> None:
        self._staged = tuple(staged or [])
        self._tracked = tuple(tracked or [])
        self._changed = tuple(changed or [])
        self.calls: list[str] = []
        self.refs: list[str] = []

    def staged_files(self) -> tuple[str, ...]:
        self.calls.append("staged")
        return self._staged

    def tracked_files(self) -> tuple[str, ...]:
        self.calls.append("tracked")
        return self._tracked

    def changed_since(self, ref: str) -> tuple[str, ...]:
        self.calls.append("changed")
        self.refs.append(ref)
        return self._changed


def _hook(
    hook_id: str,
    *,
    files: str | None = None,
    exclude: str | None = None,
    pass_files: bool = True,
) -> HookDef:
    data: dict[str, object] = {
        "id": hook_id,
        "from": "system",
        "run": "tool",
        "pass-files": pass_files,
    }
    if files is not None:
        data["files"] = files
    if exclude is not None:
        data["exclude"] = exclude
    return HookDef.model_validate(data)


def _paths(*names: str) -> tuple[Path, ...]:
    return tuple(Path(n) for n in names)


# ── source selection ──────────────────────────────────────────────


def test_default_uses_staged_files() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py", "b.txt"], tracked=["a.py", "b.txt", "c.md"])
    # Act
    result = resolve_changeset([_hook("lint")], git=git)
    # Assert
    assert isinstance(result, Changeset)
    assert result.files == _paths("a.py", "b.txt")
    assert git.calls == ["staged"]


def test_all_files_uses_tracked_files() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py"], tracked=["a.py", "b.txt", "c.md"])
    # Act
    result = resolve_changeset([_hook("lint")], all_files=True, git=git)
    # Assert
    assert result.files == _paths("a.py", "b.txt", "c.md")
    assert git.calls == ["tracked"]


def test_base_uses_changed_since_and_forwards_the_ref() -> None:
    # Arrange
    git = FakeGitClient(staged=["staged.py"], tracked=["all.py"], changed=["since.py"])
    # Act
    result = resolve_changeset([_hook("lint")], base="main", git=git)
    # Assert — the ref decides the file set, and it is forwarded verbatim
    assert result.files == _paths("since.py")
    assert git.calls == ["changed"]
    assert git.refs == ["main"]


def test_base_takes_precedence_over_all_files() -> None:
    # Arrange
    git = FakeGitClient(staged=["staged.py"], tracked=["all.py"], changed=["since.py"])
    # Act — the CLI rejects this combination, but the library defines precedence
    result = resolve_changeset([_hook("lint")], all_files=True, base="main", git=git)
    # Assert
    assert result.files == _paths("since.py")
    assert git.calls == ["changed"]


# ── per-hook file routing ─────────────────────────────────────────


def test_files_glob_filters_the_hook_subset() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py", "b.txt", "c.py"])
    hook = _hook("lint", files="*.py")
    # Act
    result = resolve_changeset([hook], git=git)
    # Assert — overall changeset unchanged; hook gets only .py files
    assert result.files == _paths("a.py", "b.txt", "c.py")
    assert result.files_by_hook["lint"] == _paths("a.py", "c.py")


def test_files_none_routes_the_whole_changeset() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py", "b.txt"])
    # Act
    result = resolve_changeset([_hook("lint")], git=git)
    # Assert
    assert result.files_by_hook["lint"] == _paths("a.py", "b.txt")


def test_pass_files_false_routes_no_files() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py", "b.py"])
    hook = _hook("once", pass_files=False)
    # Act
    result = resolve_changeset([hook], git=git)
    # Assert — hook gets nothing, but the changeset itself is still populated
    assert result.files_by_hook["once"] == ()
    assert result.files == _paths("a.py", "b.py")


def test_glob_matches_nested_paths() -> None:
    # Arrange — fnmatch treats '/' like any char, so '*.py' matches at any depth
    git = FakeGitClient(staged=["src/pkg/mod.py", "README.md"])
    hook = _hook("lint", files="*.py")
    # Act
    result = resolve_changeset([hook], git=git)
    # Assert
    assert result.files_by_hook["lint"] == _paths("src/pkg/mod.py")


def test_exclude_glob_removes_matching_files() -> None:
    # Arrange — lint all .py but drop tests
    git = FakeGitClient(staged=["src/app.py", "tests/test_app.py", "src/util.py"])
    hook = _hook("lint", files="*.py", exclude="tests/*")
    # Act
    result = resolve_changeset([hook], git=git)
    # Assert — the excluded test file is gone; the rest remain
    assert result.files_by_hook["lint"] == _paths("src/app.py", "src/util.py")


def test_exclude_applies_without_a_files_glob() -> None:
    # Arrange — no files glob (whole changeset), but exclude a subtree
    git = FakeGitClient(staged=["a.py", "vendor/x.py", "b.py"])
    hook = _hook("lint", exclude="vendor/*")
    # Act
    result = resolve_changeset([hook], git=git)
    # Assert
    assert result.files_by_hook["lint"] == _paths("a.py", "b.py")


def test_multiple_hooks_each_get_their_own_subset() -> None:
    # Arrange
    git = FakeGitClient(staged=["a.py", "b.js", "c.py"])
    py = _hook("py", files="*.py")
    js = _hook("js", files="*.js")
    once = _hook("once", pass_files=False)
    # Act
    result = resolve_changeset([py, js, once], git=git)
    # Assert
    assert result.files_by_hook == {
        "py": _paths("a.py", "c.py"),
        "js": _paths("b.js"),
        "once": (),
    }
