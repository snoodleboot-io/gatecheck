"""Acceptance tests for STY-0005 — resolving `project` / `system` sources.

Mirrors the acceptance criteria in
``planning/features/FEAT-0002-source-resolution/stories/STY-0005-resolve-project-system-sources.md``
and the LOCKED contract in
``planning/build-plans/0005-architecture-decision.md`` §4/§5:

- End-to-end-ish but still HERMETIC: a realistic fake project tree
  (``.venv/bin/ruff``) is built under ``tmp_path`` and resolved via a
  ``ProjectSource``; a ``SystemSource`` is resolved against an injected ``PATH``.
- AC-13 guard: a resolution failure is a plain ``SourceResolutionError`` and is
  NEVER wrapped as ``ConfigError`` — ``load_config`` of a config whose tool is
  absent still SUCCEEDS. This proves the "no ConfigError mapping" boundary (§5).

No mocks: fake executables are real files written to ``tmp_path`` (``chmod`` +x);
``load_config`` is exercised against a real ``check.toml``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from gatecheck.config import ConfigError, load_config
from gatecheck.sources import (
    ProjectSource,
    SourceResolutionError,
    SystemSource,
    resolve_source,
)
from gatecheck.venv import bin_dir_name


def _make_executable(path: Path) -> Path:
    """Create ``path`` as a regular, executable file (a fake tool binary)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".bat")
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return path


# ---------------------------------------------------------------------------
# Project source — realistic fake .venv tree resolved end-to-end
# ---------------------------------------------------------------------------


def test_project_source_resolves_in_fake_venv_tree(tmp_path: Path) -> None:
    """Given a project tree with an executable .venv/bin/ruff,
    When resolve_source is called for a ProjectSource,
    Then it returns the absolute .venv path with origin 'project'.

    Covers STY-0005 AC-4 / AC-11 end-to-end.
    """
    # Arrange — a realistic project layout under tmp_path.
    project = tmp_path / "myproject"
    (project / "src").mkdir(parents=True)
    (project / "check.toml").write_text(
        '[[hook]]\nid = "ruff"\nfrom = "project"\nrun = "ruff check"\n',
        encoding="utf-8",
    )
    ruff = _make_executable(project / ".venv" / bin_dir_name() / "ruff")

    # Act — no VIRTUAL_ENV; discovery falls to <root>/.venv.
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=project,
        environ={"PATH": "/nonexistent"},
    )

    # Assert
    assert result.origin == "project"
    assert result.executable == ruff.resolve()
    assert result.executable.is_absolute()
    assert result.executable.exists()


def test_project_source_absent_raises_source_resolution_error(tmp_path: Path) -> None:
    """Given a project tree with NO .venv and no VIRTUAL_ENV,
    When resolve_source is called for a ProjectSource,
    Then it raises SourceResolutionError naming the tool (not a ConfigError).

    Covers STY-0005 AC-6 / AC-13.
    """
    # Arrange
    project = tmp_path / "myproject"
    project.mkdir()

    # Act / Assert
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(
            ProjectSource(),
            "ruff",
            workspace_root=project,
            environ={"PATH": "/nonexistent"},
        )

    # Assert — a plain SourceResolutionError, never a ConfigError.
    assert not isinstance(exc_info.value, ConfigError)
    assert exc_info.value.tool == "ruff"
    assert exc_info.value.kind == "project"


# ---------------------------------------------------------------------------
# System source — resolved against an injected PATH
# ---------------------------------------------------------------------------


def test_system_source_resolves_against_injected_path(tmp_path: Path) -> None:
    """Given an executable on an injected PATH,
    When resolve_source is called for a SystemSource,
    Then it returns the absolute located path with origin 'system'.

    Covers STY-0005 AC-1 end-to-end (hermetic — no real system tools).
    """
    # Arrange
    bin_dir = tmp_path / "tools"
    tool = _make_executable(bin_dir / "org-linter")

    # Act
    result = resolve_source(SystemSource(), "org-linter", environ={"PATH": str(bin_dir)})

    # Assert
    assert result.origin == "system"
    assert result.executable == tool.resolve()
    assert result.executable.is_absolute()
    assert result.executable.exists()


# ---------------------------------------------------------------------------
# AC-13 — resolution failure does NOT surface via load_config
# ---------------------------------------------------------------------------


def test_load_config_succeeds_even_when_tool_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a valid check.toml whose hook's tool is not installed anywhere,
    When load_config runs,
    Then it SUCCEEDS — resolution is a runtime concern, not a config error.

    Covers STY-0005 AC-13: SourceResolutionError does not map to ConfigError,
    and load_config never triggers resolution.
    """
    # Arrange — a syntactically valid config; the tool `definitely-not-installed`
    # exists nowhere, but that is a resolve-time, not load-time, condition.
    cfg = tmp_path / "check.toml"
    cfg.write_text(
        "[[hook]]\n"
        'id   = "missing"\n'
        'from = "system"\n'
        'run  = "definitely-not-installed --check"\n'
        "pass-files = false\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    # Act — loading must NOT raise (no resolution performed at load time).
    result = load_config(Path("check.toml"))

    # Assert — the config loaded cleanly with the hook's `from`/`run` intact.
    assert [h.from_ for h in result.hook] == ["system"]
    assert result.hook[0].run == "definitely-not-installed --check"

    # And resolving that absent tool raises SourceResolutionError, not ConfigError.
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(
            SystemSource(),
            "definitely-not-installed",
            environ={"PATH": str(empty_bin)},
        )
    assert not isinstance(exc_info.value, ConfigError)
    assert exc_info.value.reason == "not found on PATH"
