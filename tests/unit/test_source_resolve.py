"""Unit tests for hooksmith.sources.resolve_source (STY-0005 / TSK-005).

Contract under test is LOCKED by
``planning/build-plans/0005-architecture-decision.md``:

- §3: frozen pydantic ``ResolvedTool`` (``tool`` / ``executable`` / ``origin``).
- §4: ``resolve_source`` signature, the ``match`` over the ``ParsedSource``
  union, the system / project precedence rules, and the EXACT ``reason`` message
  table (assertions here pin the LOCKED text so any code drift fails).
- §5: ``SourceResolutionError(ValueError)`` with message
  ``cannot resolve '<tool>' from <kind> source: <reason>`` — it does NOT map to
  ``ConfigError``.

``resolve_source`` is a pure function of its inputs + filesystem state (§4
"Determinism / purity", AC-9/AC-10): these tests use NO mocks. They are hermetic
— fake executables are built under ``tmp_path`` (a regular file, ``chmod`` +x so
``os.access(X_OK)`` passes) and ``PATH`` / ``VIRTUAL_ENV`` / ``workspace_root``
are injected explicitly so nothing depends on the real machine's tools. AAA
structure throughout.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from hooksmith.sources import (
    ProjectSource,
    PyPISource,
    ResolvedTool,
    SourceResolutionError,
    SystemSource,
    UnsupportedSource,
    resolve_source,
)
from hooksmith.venv import bin_dir_name

# ---------------------------------------------------------------------------
# Helpers — build hermetic fake executables under tmp_path.
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> Path:
    """Create ``path`` as a regular file and make it executable.

    Returns the same path so callers can inline it. ``os.access(path, os.X_OK)``
    will be True, so it qualifies under the resolver's file+executable check.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".bat")
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return path


def _make_non_executable(path: Path) -> Path:
    """Create ``path`` as a regular file WITHOUT the executable bit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not executable\n", encoding="utf-8")
    path.chmod(0o644)
    return path


# ---------------------------------------------------------------------------
# AC-1 — system source found on PATH
# ---------------------------------------------------------------------------


def test_system_source_found_returns_absolute_executable(tmp_path: Path) -> None:
    # Arrange — a fake `bin/` on an injected PATH holding an executable `tool`.
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "tool")

    # Act
    result = resolve_source(SystemSource(), "tool", environ={"PATH": str(bin_dir)})

    # Assert
    assert isinstance(result, ResolvedTool)
    assert result.tool == "tool"
    assert result.origin == "system"
    assert result.executable == exe.resolve()
    assert result.executable.is_absolute()


def test_system_source_result_matches_shutil_which_resolved(tmp_path: Path) -> None:
    # AC-1: executable equals Path(shutil.which(tool)).resolve().
    # Arrange
    import shutil

    bin_dir = tmp_path / bin_dir_name()
    _make_executable(bin_dir / "widget")
    path_value = str(bin_dir)

    # Act
    result = resolve_source(SystemSource(), "widget", environ={"PATH": path_value})

    # Assert
    located = shutil.which("widget", path=path_value)
    assert located is not None
    assert result.executable == Path(located).resolve()
    assert result.executable.exists()


# ---------------------------------------------------------------------------
# AC-2 — system source absent from PATH
# ---------------------------------------------------------------------------


def test_system_source_absent_raises_not_found_on_path(tmp_path: Path) -> None:
    # Arrange — an EMPTY bin dir is the only entry on PATH.
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    reason = "not found on PATH"

    # Act / Assert
    with pytest.raises(SourceResolutionError, match=re.escape(reason)):
        resolve_source(SystemSource(), "no-such-tool", environ={"PATH": str(empty_bin)})


def test_system_source_absent_full_message_and_fields(tmp_path: Path) -> None:
    # AC-2 / AC-12: full message form + structured fields.
    # Arrange
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()

    # Act
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(SystemSource(), "ghost", environ={"PATH": str(empty_bin)})

    # Assert
    err = exc_info.value
    assert str(err) == "cannot resolve 'ghost' from system source: not found on PATH"
    assert err.tool == "ghost"
    assert err.kind == "system"
    assert err.reason == "not found on PATH"


# ---------------------------------------------------------------------------
# AC-7 (system side) — a non-executable file on PATH is not a match
# ---------------------------------------------------------------------------


def test_system_source_non_executable_on_path_is_not_found(tmp_path: Path) -> None:
    # Arrange — file exists on PATH but lacks the executable bit.
    bin_dir = tmp_path / bin_dir_name()
    _make_non_executable(bin_dir / "tool")

    # Act / Assert — shutil.which requires X_OK, so this is not-found.
    with pytest.raises(SourceResolutionError, match=re.escape("not found on PATH")):
        resolve_source(SystemSource(), "tool", environ={"PATH": str(bin_dir)})


# ---------------------------------------------------------------------------
# AC-3 — project source via active VIRTUAL_ENV
# ---------------------------------------------------------------------------


def test_project_source_via_virtualenv_resolves(tmp_path: Path) -> None:
    # Arrange — an executable inside $VIRTUAL_ENV/bin.
    venv = tmp_path / "venv"
    exe = _make_executable(venv / bin_dir_name() / "ruff")
    root = tmp_path / "workspace"  # no .venv here
    root.mkdir()

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=root,
        environ={"VIRTUAL_ENV": str(venv), "PATH": "/nonexistent"},
    )

    # Assert
    assert result.origin == "project"
    assert result.tool == "ruff"
    assert result.executable == exe.resolve()
    assert result.executable.is_absolute()


# ---------------------------------------------------------------------------
# AC-4 — project source via discovered <root>/.venv (no VIRTUAL_ENV)
# ---------------------------------------------------------------------------


def test_project_source_via_dot_venv_resolves(tmp_path: Path) -> None:
    # Arrange — executable in <root>/.venv/bin, no VIRTUAL_ENV in environ.
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=root,
        environ={"PATH": "/nonexistent"},
    )

    # Assert
    assert result.origin == "project"
    assert result.executable == exe.resolve()
    assert result.executable.is_absolute()


def test_project_source_defaults_workspace_root_to_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-4 (default): workspace_root=None -> Path.cwd() resolved inside the call.
    # Arrange
    exe = _make_executable(tmp_path / ".venv" / bin_dir_name() / "ruff")
    monkeypatch.chdir(tmp_path)

    # Act — no workspace_root passed; environ has no VIRTUAL_ENV.
    result = resolve_source(ProjectSource(), "ruff", environ={"PATH": "/nonexistent"})

    # Assert
    assert result.origin == "project"
    assert result.executable == exe.resolve()


# ---------------------------------------------------------------------------
# AC-5 — precedence: active VIRTUAL_ENV wins over <root>/.venv
# ---------------------------------------------------------------------------


def test_project_source_precedence_virtualenv_wins_over_dot_venv(tmp_path: Path) -> None:
    # Arrange — the tool exists in BOTH locations.
    venv = tmp_path / "active-venv"
    venv_exe = _make_executable(venv / bin_dir_name() / "ruff")
    root = tmp_path / "workspace"
    _make_executable(root / ".venv" / bin_dir_name() / "ruff")

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=root,
        environ={"VIRTUAL_ENV": str(venv), "PATH": "/nonexistent"},
    )

    # Assert — the VIRTUAL_ENV candidate is chosen.
    assert result.executable == venv_exe.resolve()
    assert result.executable != (root / ".venv" / bin_dir_name() / "ruff").resolve()


def test_project_source_empty_virtualenv_falls_back_to_dot_venv(tmp_path: Path) -> None:
    # §4: VIRTUAL_ENV qualifies only if set AND non-empty; "" -> skip to .venv.
    # Arrange
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=root,
        environ={"VIRTUAL_ENV": "", "PATH": "/nonexistent"},
    )

    # Assert
    assert result.executable == exe.resolve()


# ---------------------------------------------------------------------------
# AC-7 (project side) — a non-executable candidate does not qualify
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX exec-bit; os.access(X_OK) is always True on Windows"
)
def test_project_source_non_executable_candidate_skipped(tmp_path: Path) -> None:
    # Arrange — <root>/.venv/bin/ruff exists but is NOT executable.
    root = tmp_path / "workspace"
    _make_non_executable(root / ".venv" / bin_dir_name() / "ruff")
    reason = _PROJECT_ABSENT_REASON

    # Act / Assert — falls through to not-found rather than returning it.
    with pytest.raises(SourceResolutionError, match=re.escape(reason)):
        resolve_source(
            ProjectSource(),
            "ruff",
            workspace_root=root,
            environ={"PATH": "/nonexistent"},
        )


@pytest.mark.skipif(
    os.name == "nt", reason="POSIX exec-bit; os.access(X_OK) is always True on Windows"
)
def test_project_source_non_executable_in_virtualenv_falls_through(tmp_path: Path) -> None:
    # AC-7: a non-executable $VIRTUAL_ENV candidate does not short-circuit; the
    # executable .venv candidate is used instead.
    # Arrange
    venv = tmp_path / "active-venv"
    _make_non_executable(venv / bin_dir_name() / "ruff")
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=root,
        environ={"VIRTUAL_ENV": str(venv), "PATH": "/nonexistent"},
    )

    # Assert
    assert result.executable == exe.resolve()


# ---------------------------------------------------------------------------
# AC-7 (project side) — non-file candidates (dir / broken symlink) are skipped
# ---------------------------------------------------------------------------

_PROJECT_ABSENT_REASON = (
    f"not found in project environment "
    f"(checked $VIRTUAL_ENV/{bin_dir_name()} and <workspace_root>/.venv/{bin_dir_name()})"
)


def test_project_source_directory_named_like_tool_is_skipped(tmp_path: Path) -> None:
    # A candidate path that is a DIRECTORY named <tool> must not qualify: the
    # `is_file()` check is False for a directory, so resolution falls through.
    # Arrange
    root = tmp_path / "workspace"
    (root / ".venv" / bin_dir_name() / "ruff").mkdir(parents=True)

    # Act / Assert
    with pytest.raises(SourceResolutionError, match=re.escape(_PROJECT_ABSENT_REASON)):
        resolve_source(
            ProjectSource(), "ruff", workspace_root=root, environ={"PATH": "/nonexistent"}
        )


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privileges on Windows")
def test_project_source_broken_symlink_candidate_is_skipped(tmp_path: Path) -> None:
    # A broken symlink at the candidate path must not qualify: `is_file()` follows
    # the link and returns False for a dangling target.
    # Arrange
    root = tmp_path / "workspace"
    bin_dir = root / ".venv" / bin_dir_name()
    bin_dir.mkdir(parents=True)
    (bin_dir / "ruff").symlink_to(tmp_path / "does-not-exist")

    # Act / Assert
    with pytest.raises(SourceResolutionError, match=re.escape(_PROJECT_ABSENT_REASON)):
        resolve_source(
            ProjectSource(), "ruff", workspace_root=root, environ={"PATH": "/nonexistent"}
        )


# ---------------------------------------------------------------------------
# AC-6 — project source absent -> LOCKED literal reason (NOT interpolated)
# ---------------------------------------------------------------------------


def test_project_source_absent_raises_literal_reason(tmp_path: Path) -> None:
    # Arrange — neither $VIRTUAL_ENV/bin nor <root>/.venv/bin has the tool.
    root = tmp_path / "workspace"
    root.mkdir()
    reason = _PROJECT_ABSENT_REASON

    # Act
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(
            ProjectSource(),
            "ruff",
            workspace_root=root,
            environ={"PATH": "/nonexistent"},
        )

    # Assert — the reason is the LITERAL placeholder text, not interpolated paths.
    err = exc_info.value
    assert err.reason == reason
    assert err.kind == "project"
    assert str(err) == f"cannot resolve 'ruff' from project source: {reason}"
    # The literal placeholders must survive verbatim (no path interpolation).
    assert f"$VIRTUAL_ENV/{bin_dir_name()}" in str(err)
    assert f"<workspace_root>/.venv/{bin_dir_name()}" in str(err)
    assert str(root) not in str(err)


# ---------------------------------------------------------------------------
# AC-9 — no filesystem writes: a missing .venv is NOT created
# ---------------------------------------------------------------------------


def test_project_resolution_failure_does_not_create_venv(tmp_path: Path) -> None:
    # Arrange — a bare workspace root with no .venv.
    root = tmp_path / "workspace"
    root.mkdir()

    # Act
    with pytest.raises(SourceResolutionError):
        resolve_source(
            ProjectSource(),
            "ruff",
            workspace_root=root,
            environ={"PATH": "/nonexistent"},
        )

    # Assert — resolution performed no writes; .venv was NOT created.
    assert not (root / ".venv").exists()
    assert list(root.iterdir()) == []


# ---------------------------------------------------------------------------
# AC-8 — pypi / unsupported rejected (typed error, no network, no crash)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "tool", "kind", "reason"),
    [
        (
            PyPISource(requirement="ruff", registry=None),
            "ruff",
            "pypi",
            "pypi source resolution is delegated to Environments (STY-0006), not handled here",
        ),
        (
            UnsupportedSource(scheme="docker"),
            "x",
            "unsupported",
            "'docker' sources are not supported",
        ),
        (
            UnsupportedSource(scheme="git"),
            "x",
            "unsupported",
            "'git' sources are not supported",
        ),
        (
            UnsupportedSource(scheme="local"),
            "lint",
            "unsupported",
            "'local' sources are not supported",
        ),
    ],
)
def test_non_resolvable_sources_raise_with_locked_reason(
    source: PyPISource | UnsupportedSource, tool: str, kind: str, reason: str
) -> None:
    # AC-8: pypi and unsupported each raise SourceResolutionError immediately.
    # Arrange / Act
    with pytest.raises(SourceResolutionError) as exc_info:
        resolve_source(source, tool)

    # Assert — exact reason + full message + structured fields.
    err = exc_info.value
    assert err.reason == reason
    assert err.kind == kind
    assert err.tool == tool
    assert str(err) == f"cannot resolve '{tool}' from {kind} source: {reason}"


# ---------------------------------------------------------------------------
# AC-10 — determinism: two calls return equal results
# ---------------------------------------------------------------------------


def test_resolution_is_deterministic_for_success(tmp_path: Path) -> None:
    # Arrange
    root = tmp_path / "workspace"
    _make_executable(root / ".venv" / bin_dir_name() / "ruff")
    environ = {"PATH": "/nonexistent"}

    # Act
    first = resolve_source(ProjectSource(), "ruff", workspace_root=root, environ=environ)
    second = resolve_source(ProjectSource(), "ruff", workspace_root=root, environ=environ)

    # Assert — equal (frozen pydantic models compare by value).
    assert first == second


def test_resolution_is_deterministic_for_failure(tmp_path: Path) -> None:
    # AC-10: the same not-found error text on every call.
    # Arrange
    root = tmp_path / "workspace"
    root.mkdir()

    # Act
    messages: list[str] = []
    for _ in range(2):
        with pytest.raises(SourceResolutionError) as exc_info:
            resolve_source(
                ProjectSource(), "ruff", workspace_root=root, environ={"PATH": "/nonexistent"}
            )
        messages.append(str(exc_info.value))

    # Assert
    assert messages[0] == messages[1]


# ---------------------------------------------------------------------------
# AC-10 (purity) — PATH is read from the injected environ, never the ambient env
# ---------------------------------------------------------------------------


def test_system_source_ignores_ambient_path_when_environ_lacks_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The resolver must read PATH only from the injected `environ` (falling back to
    # os.defpath), never the ambient process env. Put a tool on the REAL PATH, then
    # resolve with an environ that has NO PATH key -> it must NOT find it.
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    _make_executable(bin_dir / "gc-uniquetool")
    monkeypatch.setenv("PATH", str(bin_dir))  # ambient PATH now contains the tool

    # Act / Assert — injected environ lacks PATH -> os.defpath fallback, not ambient.
    with pytest.raises(SourceResolutionError, match=re.escape("not found on PATH")):
        resolve_source(SystemSource(), "gc-uniquetool", environ={})


# ---------------------------------------------------------------------------
# AC-11 — executable is always absolute
# ---------------------------------------------------------------------------


def test_resolved_executable_is_always_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Arrange — resolve via a genuinely RELATIVE workspace_root (cwd-relative) to
    # prove the resolver absolutises it, not just that tmp_path is already absolute.
    monkeypatch.chdir(tmp_path)
    exe = _make_executable(tmp_path / "workspace" / ".venv" / bin_dir_name() / "ruff")
    relative_root = Path("workspace")
    assert not relative_root.is_absolute()

    # Act
    result = resolve_source(
        ProjectSource(),
        "ruff",
        workspace_root=relative_root,
        environ={"PATH": "/nonexistent"},
    )

    # Assert
    assert result.executable.is_absolute()
    assert result.executable == exe.resolve()


# ---------------------------------------------------------------------------
# AC-12 — SourceResolutionError type + message form
# ---------------------------------------------------------------------------


def test_source_resolution_error_is_value_error_subclass() -> None:
    # AC-12
    # Arrange / Act / Assert
    assert issubclass(SourceResolutionError, ValueError)


def test_source_resolution_error_caught_as_value_error(tmp_path: Path) -> None:
    # AC-12: existing `except ValueError` handlers still catch it.
    # Arrange
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()

    # Act
    with pytest.raises(ValueError) as exc_info:
        resolve_source(SystemSource(), "ghost", environ={"PATH": str(empty_bin)})

    # Assert
    assert isinstance(exc_info.value, SourceResolutionError)


@pytest.mark.parametrize(
    ("tool", "kind", "reason", "expected"),
    [
        (
            "ruff",
            "system",
            "not found on PATH",
            "cannot resolve 'ruff' from system source: not found on PATH",
        ),
        (
            "x",
            "unsupported",
            "'docker' sources are not supported",
            "cannot resolve 'x' from unsupported source: 'docker' sources are not supported",
        ),
    ],
)
def test_source_resolution_error_message_form(
    tool: str, kind: str, reason: str, expected: str
) -> None:
    # AC-12: cannot resolve '<tool>' from <kind> source: <reason>.
    # Arrange / Act
    err = SourceResolutionError(tool, kind, reason)

    # Assert
    assert str(err) == expected
    assert err.tool == tool
    assert err.kind == kind
    assert err.reason == reason


# ---------------------------------------------------------------------------
# origin / match on result
# ---------------------------------------------------------------------------


def test_result_origin_is_matchable(tmp_path: Path) -> None:
    # The output carries an `origin` discriminant for runner/cache explainability.
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    _make_executable(bin_dir / "tool")

    # Act
    result = resolve_source(SystemSource(), "tool", environ={"PATH": str(bin_dir)})

    # Assert
    origin: str
    match result:
        case ResolvedTool(origin="system"):
            origin = "system"
        case ResolvedTool(origin="project"):
            origin = "project"
    assert origin == "system"


# ---------------------------------------------------------------------------
# AC-14 — public import contract
# ---------------------------------------------------------------------------


def test_public_import_surface() -> None:
    # AC-14: the three new symbols import from hooksmith.sources, and the
    # STY-0004 symbols still import (no regression to the facade).
    # Arrange / Act
    from hooksmith.sources import (
        ParsedSource as _ParsedSource,
    )
    from hooksmith.sources import (
        ProjectSource as _ProjectSource,
    )
    from hooksmith.sources import (
        PyPISource as _PyPISource,
    )
    from hooksmith.sources import (
        ResolvedTool as _ResolvedTool,
    )
    from hooksmith.sources import (
        SourceResolutionError as _SourceResolutionError,
    )
    from hooksmith.sources import (
        SourceSpecError as _SourceSpecError,
    )
    from hooksmith.sources import (
        SystemSource as _SystemSource,
    )
    from hooksmith.sources import (
        UnsupportedSource as _UnsupportedSource,
    )
    from hooksmith.sources import (
        parse_source as _parse_source,
    )
    from hooksmith.sources import (
        resolve_source as _resolve_source,
    )

    # Assert
    assert callable(_resolve_source)
    assert isinstance(_ResolvedTool, type)
    assert issubclass(_SourceResolutionError, ValueError)
    # STY-0004 surface intact.
    assert callable(_parse_source)
    assert isinstance(_PyPISource, type)
    assert isinstance(_ProjectSource, type)
    assert isinstance(_SystemSource, type)
    assert isinstance(_UnsupportedSource, type)
    assert issubclass(_SourceSpecError, ValueError)
    assert _ParsedSource is not None
