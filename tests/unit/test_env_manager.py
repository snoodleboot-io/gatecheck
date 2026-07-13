"""Unit tests for gatecheck.env.EnvManager (STY-0007 / TSK-007).

Contract under test is LOCKED by
``planning/build-plans/0007-architecture-decision.md``:

- §3: frozen dataclass ``ResolvedEnv(bin_dir, cache_key)`` (unchanged shape).
- §4: ``EnvError(ValueError)`` with structured ``hook_id`` / ``reason`` and the
  message ``cannot resolve environment for hook '<id>': <reason>``; the EXACT
  ``reason`` text table (pypi deferred / unsupported / tool-name derivation) is
  pinned verbatim below so any code drift fails. The two FEAT-0002 errors
  (``SourceResolutionError`` / ``SourceSpecError``) propagate UNWRAPPED.
- §5: ``resolve`` dispatch, the ``_derive_tool`` rule (``shlex.split(run)[0]``).
- §6: the ``_cache_key`` formula
  ``sha256("env-v1\\n" + origin + "\\n" + str(executable))``.

``EnvManager.resolve`` is a pure function of ``(hook, workspace_root, environ,
filesystem state)`` (§8). These tests use NO mocks beyond a subprocess spy — they
are hermetic: fake executables are built under ``tmp_path`` (a regular file,
``chmod`` +x so ``os.access(X_OK)`` passes) and ``PATH`` / ``VIRTUAL_ENV`` /
``workspace_root`` are injected via the constructor so nothing depends on the
real machine's tools. AAA structure throughout. Mirrors
``tests/unit/test_source_resolve.py``.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvError, EnvManager, ResolvedEnv
from gatecheck.registry import RegistryError
from gatecheck.sources import SourceResolutionError, SourceSpecError
from gatecheck.venv import bin_dir_name

_CACHE_KEY_SCHEME = "env-v1"

# ---------------------------------------------------------------------------
# Helpers — build hermetic fake executables + HookDefs.
# ---------------------------------------------------------------------------


def _make_executable(path: Path) -> Path:
    """Create ``path`` as a regular file and make it executable.

    ``os.access(path, os.X_OK)`` will be True, so it qualifies under the
    resolver's file+executable check. Returns the same path for inlining.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        path = path.with_suffix(".bat")
        path.write_text("@echo off\r\nexit /b 0\r\n", encoding="utf-8")
    else:
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
    return path


def _hook(hook_id: str, from_spec: str, run: str) -> HookDef:
    """Build a valid HookDef from the three fields resolve() reads."""
    return HookDef.model_validate({"id": hook_id, "from": from_spec, "run": run})


def _expected_cache_key(origin: str, executable: Path) -> str:
    material = "\n".join([_CACHE_KEY_SCHEME, origin, str(executable)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# AC-1 — system resolve: from = "system", tool located on injected PATH.
# ---------------------------------------------------------------------------


def test_system_resolve_returns_resolved_env_with_bin_dir_parent(tmp_path: Path) -> None:
    # Arrange — an executable `ruff` on an injected PATH.
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    result = manager.resolve(_hook("lint", "system", "ruff check"))

    # Assert
    assert isinstance(result, ResolvedEnv)
    assert result.bin_dir == exe.resolve().parent
    assert len(result.cache_key) == 64
    assert result.cache_key == result.cache_key.lower()
    assert re.fullmatch(r"[0-9a-f]{64}", result.cache_key) is not None


def test_system_resolve_ignores_extra_argv_tokens(tmp_path: Path) -> None:
    # AC-3: only the first shlex token names the tool; extra argv is ignored.
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    result = manager.resolve(_hook("lint", "system", "ruff check --fix src tests"))

    # Assert
    assert result.bin_dir == exe.resolve().parent


# ---------------------------------------------------------------------------
# AC-2 — project resolve: from = "project", <root>/.venv/bin/<tool>.
# ---------------------------------------------------------------------------


def test_project_resolve_via_dot_venv_returns_bin_dir(tmp_path: Path) -> None:
    # Arrange — an executable in <root>/.venv/bin, no VIRTUAL_ENV.
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")
    manager = EnvManager(workspace_root=root, environ={"PATH": "/nonexistent"})

    # Act
    result = manager.resolve(_hook("lint", "project", "ruff check"))

    # Assert
    assert result.bin_dir == exe.resolve().parent
    assert re.fullmatch(r"[0-9a-f]{64}", result.cache_key) is not None


def test_project_resolve_via_virtualenv_returns_bin_dir(tmp_path: Path) -> None:
    # AC-2: from = "project" also resolves via an injected $VIRTUAL_ENV/bin.
    # Arrange
    venv = tmp_path / "venv"
    exe = _make_executable(venv / bin_dir_name() / "ruff")
    root = tmp_path / "workspace"
    root.mkdir()
    manager = EnvManager(
        workspace_root=root,
        environ={"VIRTUAL_ENV": str(venv), "PATH": "/nonexistent"},
    )

    # Act
    result = manager.resolve(_hook("lint", "project", "ruff check"))

    # Assert
    assert result.bin_dir == exe.resolve().parent


# ---------------------------------------------------------------------------
# AC-4 / AC-5 — cache_key formula + determinism.
# ---------------------------------------------------------------------------


def test_cache_key_matches_locked_formula(tmp_path: Path) -> None:
    # AC-4: sha256("env-v1\n<origin>\n<absolute executable path>").
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    result = manager.resolve(_hook("lint", "system", "ruff check"))

    # Assert — recompute the expected digest independently.
    expected = _expected_cache_key("system", exe.resolve())
    assert result.cache_key == expected


def test_cache_key_is_deterministic_and_resolved_env_equal(tmp_path: Path) -> None:
    # AC-5: two resolves with identical inputs yield equal cache_key + ResolvedEnv.
    # Arrange
    bin_dir = tmp_path / bin_dir_name()
    _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})
    hook = _hook("lint", "system", "ruff check")

    # Act
    first = manager.resolve(hook)
    second = manager.resolve(hook)

    # Assert
    assert first.cache_key == second.cache_key
    assert first == second  # frozen dataclass -> structural equality


def test_cache_key_differs_for_different_executable(tmp_path: Path) -> None:
    # AC-4: a different resolved executable path yields a different key.
    # Arrange — two distinct bin dirs, each with its own `ruff`.
    bin_a = tmp_path / "a"
    bin_b = tmp_path / "b"
    _make_executable(bin_a / "ruff")
    _make_executable(bin_b / "ruff")

    # Act
    key_a = (
        EnvManager(environ={"PATH": str(bin_a)}).resolve(_hook("lint", "system", "ruff")).cache_key
    )
    key_b = (
        EnvManager(environ={"PATH": str(bin_b)}).resolve(_hook("lint", "system", "ruff")).cache_key
    )

    # Assert
    assert key_a != key_b


def test_same_executable_via_project_vs_system_keys_differently(tmp_path: Path) -> None:
    # AC-6: origin is part of the material, so the SAME executable path reached
    # via project vs system produces different cache_keys.
    # Arrange — <root>/.venv/bin is BOTH the project venv AND on PATH.
    root = tmp_path / "workspace"
    exe = _make_executable(root / ".venv" / bin_dir_name() / "ruff")
    bin_dir = exe.parent

    system_manager = EnvManager(environ={"PATH": str(bin_dir)})
    project_manager = EnvManager(workspace_root=root, environ={"PATH": "/nonexistent"})

    # Act
    system_key = system_manager.resolve(_hook("lint", "system", "ruff")).cache_key
    project_key = project_manager.resolve(_hook("lint", "project", "ruff")).cache_key

    # Assert — same executable, different origin -> different key.
    assert system_key != project_key
    assert system_key == _expected_cache_key("system", exe.resolve())
    assert project_key == _expected_cache_key("project", exe.resolve())


# ---------------------------------------------------------------------------
# pypi is built via uv (STY-0008); it no longer defers. Full build/cache coverage
# lives in test_env_manager_pypi.py. Here we assert only that the pypi branch
# delegates to the registry resolver (bypassing resolve_source) and that a
# RegistryError propagates UNWRAPPED — hermetically, via an unknown alias whose
# error is raised before any network call.
# ---------------------------------------------------------------------------


def test_pypi_unknown_alias_propagates_registry_error() -> None:
    # Arrange — an unknown alias fails at pinning, before any network/uv work.
    manager = EnvManager(environ={"PATH": "/nonexistent"})
    hook = _hook("fmt", "pypi+internal:x==1", "ruff format")

    # Act / Assert — the RegistryError is NOT re-wrapped as EnvError.
    with pytest.raises(RegistryError):
        manager.resolve(hook)


def test_pypi_source_does_not_reach_resolve_source(monkeypatch: pytest.MonkeyPatch) -> None:
    # The pypi branch delegates to resolve_pypi_source, never resolve_source. Spy on
    # the name resolve_source() imported into gatecheck.env.manager.
    # Arrange
    import gatecheck.env.manager as manager_mod

    calls: list[object] = []

    def _spy(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("resolve_source must not be called for a pypi source")

    monkeypatch.setattr(manager_mod, "resolve_source", _spy, raising=False)
    manager = EnvManager(environ={"PATH": "/nonexistent"})

    # Act / Assert — unknown alias raises RegistryError before any network call.
    with pytest.raises(RegistryError):
        manager.resolve(_hook("fmt", "pypi+internal:x==1", "ruff format"))
    assert calls == []


# ---------------------------------------------------------------------------
# AC-8 — unsupported schemes (local / git / docker) -> EnvError.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("from_spec", "scheme"),
    [
        ("docker:img", "docker"),
        ("git:https://example.com/x.git", "git"),
        ("local:./tool", "local"),
    ],
)
def test_unsupported_source_raises_env_error(from_spec: str, scheme: str) -> None:
    # AC-8: recognized-but-unsupported kinds raise EnvError echoing the scheme.
    # Arrange
    reason = f"'{scheme}' sources are not supported"
    manager = EnvManager(environ={"PATH": "/nonexistent"})
    hook = _hook("h1", from_spec, "tool run")

    # Act / Assert
    with pytest.raises(EnvError, match=re.escape(reason)) as exc_info:
        manager.resolve(hook)
    err = exc_info.value
    assert err.reason == reason
    assert err.hook_id == "h1"
    assert str(err) == f"cannot resolve environment for hook 'h1': {reason}"


# ---------------------------------------------------------------------------
# AC-9 — tool-name derivation failures -> EnvError.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("run", ["   ", "\t", " \n "])
def test_whitespace_run_raises_env_error_with_run_string(run: str) -> None:
    # AC-9: a run that yields no shlex tokens cannot derive a tool name.
    # Arrange
    reason = f"cannot derive a tool name from run = '{run}'"
    manager = EnvManager(environ={"PATH": "/nonexistent"})
    hook = _hook("h1", "system", run)

    # Act / Assert
    with pytest.raises(EnvError, match=re.escape(reason)) as exc_info:
        manager.resolve(hook)
    err = exc_info.value
    assert err.reason == reason
    assert err.hook_id == "h1"


def test_unbalanced_quote_run_raises_env_error() -> None:
    # AC-9: shlex.split raises ValueError on an unbalanced quote -> EnvError.
    # Arrange
    run = 'ruff "unbalanced'
    reason = f"cannot derive a tool name from run = '{run}'"
    manager = EnvManager(environ={"PATH": "/nonexistent"})
    hook = _hook("h1", "system", run)

    # Act / Assert
    with pytest.raises(EnvError, match=re.escape(reason)) as exc_info:
        manager.resolve(hook)
    assert exc_info.value.reason == reason


def test_quoted_run_uses_shlex_token_with_space_as_tool(tmp_path: Path) -> None:
    # AC-3: shlex semantics — a quoted program name with a space is one token.
    # Arrange — a fake executable literally named "my tool".
    bin_dir = tmp_path / bin_dir_name()
    exe = _make_executable(bin_dir / "my tool")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act — run's first shlex token is `my tool` (not `my`).
    result = manager.resolve(_hook("h1", "system", '"my tool" --x'))

    # Assert — resolution used the space-containing token, proving shlex is used.
    assert result.bin_dir == exe.resolve().parent


# ---------------------------------------------------------------------------
# AC-10 — SourceResolutionError propagates UNWRAPPED (not EnvError).
# ---------------------------------------------------------------------------


def test_system_tool_absent_propagates_source_resolution_error(tmp_path: Path) -> None:
    # AC-10: a missing tool surfaces resolve_source's typed error, NOT EnvError.
    # Arrange — an empty bin dir is the only PATH entry.
    empty_bin = tmp_path / "empty"
    empty_bin.mkdir()
    manager = EnvManager(environ={"PATH": str(empty_bin)})
    hook = _hook("lint", "system", "ghost-tool check")

    # Act / Assert
    with pytest.raises(SourceResolutionError) as exc_info:
        manager.resolve(hook)
    err = exc_info.value
    assert isinstance(err, SourceResolutionError)
    assert not isinstance(err, EnvError)
    assert err.tool == "ghost-tool"
    assert err.kind == "system"


# ---------------------------------------------------------------------------
# AC-11 — malformed `from` propagates SourceSpecError UNWRAPPED.
# ---------------------------------------------------------------------------


def test_malformed_from_propagates_source_spec_error() -> None:
    # AC-11: parse_source raises SourceSpecError for an unknown scheme; unwrapped.
    # Arrange
    manager = EnvManager(environ={"PATH": "/nonexistent"})
    hook = _hook("lint", "bogus:thing", "ruff check")

    # Act / Assert
    with pytest.raises(SourceSpecError) as exc_info:
        manager.resolve(hook)
    err = exc_info.value
    assert isinstance(err, SourceSpecError)
    assert not isinstance(err, EnvError)


# ---------------------------------------------------------------------------
# AC-12 — EnvError type / message / structured fields.
# ---------------------------------------------------------------------------


def test_env_error_is_value_error_subclass() -> None:
    # AC-12
    # Arrange / Act / Assert
    assert issubclass(EnvError, ValueError)


def test_env_error_message_form_and_fields() -> None:
    # AC-12: message form + structured hook_id / reason.
    # Arrange / Act
    err = EnvError("my-hook", "some reason")

    # Assert
    assert str(err) == "cannot resolve environment for hook 'my-hook': some reason"
    assert err.hook_id == "my-hook"
    assert err.reason == "some reason"


def test_env_error_caught_as_value_error(tmp_path: Path) -> None:
    # AC-12: existing `except ValueError` handlers still catch EnvError.
    # Arrange
    manager = EnvManager(environ={"PATH": "/nonexistent"})

    # Act
    with pytest.raises(ValueError) as exc_info:
        manager.resolve(_hook("fmt", "pypi:ruff", "ruff format"))

    # Assert
    assert isinstance(exc_info.value, EnvError)


# ---------------------------------------------------------------------------
# AC-13 / AC-16 — hermeticity: no subprocess, no venv creation.
# ---------------------------------------------------------------------------


def test_successful_resolve_spawns_no_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-13: a subprocess spy must never fire during resolve.
    # Arrange
    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("resolve must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)
    bin_dir = tmp_path / bin_dir_name()
    _make_executable(bin_dir / "ruff")
    manager = EnvManager(environ={"PATH": str(bin_dir)})

    # Act
    result = manager.resolve(_hook("lint", "system", "ruff check"))

    # Assert — reached here without the spy firing.
    assert isinstance(result, ResolvedEnv)


def test_project_miss_creates_no_venv_directory(tmp_path: Path) -> None:
    # AC-16: a failed project resolve writes nothing; no .venv is created.
    # Arrange — bare workspace root, no .venv.
    root = tmp_path / "workspace"
    root.mkdir()
    manager = EnvManager(workspace_root=root, environ={"PATH": "/nonexistent"})

    # Act
    with pytest.raises(SourceResolutionError):
        manager.resolve(_hook("lint", "project", "ruff check"))

    # Assert — no directory was created.
    assert not (root / ".venv").exists()
    assert list(root.iterdir()) == []


# ---------------------------------------------------------------------------
# AC-14 — public import contract.
# ---------------------------------------------------------------------------


def test_public_import_surface() -> None:
    # AC-14: EnvManager / ResolvedEnv / EnvError all import from gatecheck.env.
    # Arrange / Act
    from gatecheck.env import EnvError as _EnvError
    from gatecheck.env import EnvManager as _EnvManager
    from gatecheck.env import ResolvedEnv as _ResolvedEnv

    # Assert
    assert isinstance(_EnvManager, type)
    assert isinstance(_ResolvedEnv, type)
    assert issubclass(_EnvError, ValueError)
