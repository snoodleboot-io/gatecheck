"""Unit tests for gatecheck.runner.run_hook (STY-0013 / GAT-15).

Hermetic — the environment and the subprocess are dependency-injected fakes; no real
env resolution and no real process. Covers passed/failed status, argv assembly
(append vs ``{files}`` substitution, empty file list), the ``PATH`` prepend, and the
``error`` results for env-resolution and spawn failures. AAA structure throughout.
"""

from __future__ import annotations

import os
from pathlib import Path

from gatecheck.config.hook_def import HookDef
from gatecheck.env import EnvError, ResolvedEnv
from gatecheck.runner import run_hook


class FakeEnvManager:
    """Stub EnvManager: returns a fixed ResolvedEnv, or raises a chosen error."""

    def __init__(self, bin_dir: Path | None = None, error: Exception | None = None) -> None:
        self._bin_dir = bin_dir or Path("/opt/tool/bin")
        self._error = error

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        if self._error is not None:
            raise self._error
        return ResolvedEnv(bin_dir=self._bin_dir, cache_key="k")


class FakeProcessRunner:
    """Records argv/env/cwd and returns a canned (exit_code, output); or raises."""

    def __init__(
        self, exit_code: int = 0, output: str = "", error: Exception | None = None
    ) -> None:
        self._exit_code = exit_code
        self._output = output
        self._error = error
        self.argv: list[str] | None = None
        self.env: dict[str, str] | None = None

    def run(self, argv: list[str], *, env: object, cwd: object) -> tuple[int, str]:
        self.argv = argv
        self.env = dict(env)  # type: ignore[arg-type]
        if self._error is not None:
            raise self._error
        return self._exit_code, self._output


def _hook(run: str = "ruff check", hook_id: str = "lint") -> HookDef:
    return HookDef.model_validate({"id": hook_id, "from": "system", "run": run})


# ── status ────────────────────────────────────────────────────────


def test_passed_when_exit_zero() -> None:
    # Arrange
    runner = FakeProcessRunner(exit_code=0, output="ok\n")
    # Act
    result = run_hook(_hook(), [Path("a.py")], env_manager=FakeEnvManager(), runner=runner)
    # Assert
    assert result.status == "passed"
    assert result.exit_code == 0
    assert result.output == "ok\n"
    assert result.duration >= 0.0


def test_failed_when_exit_nonzero() -> None:
    # Arrange
    runner = FakeProcessRunner(exit_code=1, output="boom")
    # Act
    result = run_hook(_hook(), [], env_manager=FakeEnvManager(), runner=runner)
    # Assert
    assert result.status == "failed"
    assert result.exit_code == 1


# ── argv assembly ─────────────────────────────────────────────────


def test_files_are_appended_when_no_placeholder() -> None:
    # Arrange
    runner = FakeProcessRunner()
    # Act
    run_hook(
        _hook("ruff check"),
        [Path("a.py"), Path("b.py")],
        env_manager=FakeEnvManager(),
        runner=runner,
    )
    # Assert
    assert runner.argv == ["ruff", "check", "a.py", "b.py"]


def test_files_placeholder_is_substituted_in_place() -> None:
    # Arrange
    runner = FakeProcessRunner()
    # Act
    run_hook(
        _hook("ruff check {files} --fix"),
        [Path("a.py"), Path("b.py")],
        env_manager=FakeEnvManager(),
        runner=runner,
    )
    # Assert — placeholder replaced in place; not also appended
    assert runner.argv == ["ruff", "check", "a.py", "b.py", "--fix"]


def test_empty_file_list_appends_nothing_to_argv() -> None:
    """``run_hook`` itself adds no paths when given none.

    Note this is a statement about argv assembly only — it is *not* a no-op for the
    tool, which typically reads "no paths" as "scan everything". Preventing that is
    the planner's job: ``build_plan`` skips a ``pass-files`` hook whose glob matches
    nothing (BUG-0002), so this argv shape is not reached for file-consuming hooks.
    """
    # Arrange
    runner = FakeProcessRunner()
    # Act
    run_hook(_hook("ruff check"), [], env_manager=FakeEnvManager(), runner=runner)
    # Assert
    assert runner.argv == ["ruff", "check"]


def test_commit_msg_token_is_substituted() -> None:
    # Arrange — a commit-msg hook referencing the message file
    runner = FakeProcessRunner()
    # Act
    run_hook(
        _hook("cz check --commit-msg-file {commit-msg}"),
        [],
        env_manager=FakeEnvManager(),
        runner=runner,
        commit_msg_file=Path("/tmp/COMMIT_EDITMSG"),
    )
    # Assert — {commit-msg} replaced by the path in place
    assert runner.argv == ["cz", "check", "--commit-msg-file", "/tmp/COMMIT_EDITMSG"]


def test_commit_msg_token_stays_literal_without_a_message_file() -> None:
    # Arrange — {commit-msg} used outside a commit-msg run (a misconfiguration)
    runner = FakeProcessRunner()
    # Act
    run_hook(
        _hook("cz check {commit-msg}"),
        [],
        env_manager=FakeEnvManager(),
        runner=runner,
    )
    # Assert — no substitution; the token is passed through unchanged
    assert runner.argv == ["cz", "check", "{commit-msg}"]


def test_bin_dir_is_prepended_to_path() -> None:
    # Arrange
    runner = FakeProcessRunner()
    bin_dir = Path("/opt/ruff/bin")
    # Act
    run_hook(
        _hook(),
        [],
        env_manager=FakeEnvManager(bin_dir=bin_dir),
        runner=runner,
        environ={"PATH": "/usr/bin"},
    )
    # Assert
    assert runner.env is not None
    assert runner.env["PATH"].split(os.pathsep)[0] == str(bin_dir)


# ── error results ─────────────────────────────────────────────────


def test_env_resolution_error_becomes_error_result() -> None:
    # Arrange — env manager raises
    manager = FakeEnvManager(error=EnvError("lint", "uv unavailable"))
    # Act
    result = run_hook(_hook(), [], env_manager=manager, runner=FakeProcessRunner())
    # Assert
    assert result.status == "error"
    assert result.exit_code is None
    assert "uv unavailable" in result.output


def test_spawn_failure_becomes_error_result() -> None:
    # Arrange — the process runner cannot spawn
    runner = FakeProcessRunner(error=OSError("no such binary"))
    # Act
    result = run_hook(_hook(), [], env_manager=FakeEnvManager(), runner=runner)
    # Assert
    assert result.status == "error"
    assert result.exit_code is None
    assert "failed to execute" in result.output
