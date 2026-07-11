"""Acceptance test for run_hook against a real subprocess (STY-0013 / GAT-15).

Runs a real ``system`` hook (``echo``) end to end with the real ``EnvManager`` and
``SubprocessProcessRunner``. Marked ``integration`` and skipped when ``echo`` is not
on ``PATH``.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from gatecheck.config.hook_def import HookDef
from gatecheck.runner import run_hook

pytestmark = pytest.mark.integration


@pytest.mark.skipif(shutil.which("echo") is None, reason="echo is not on PATH")
def test_run_system_echo_hook_passes() -> None:
    # Arrange — a system hook that echoes its files
    hook = HookDef.model_validate({"id": "say", "from": "system", "run": "echo hello"})

    # Act
    result = run_hook(hook, [])

    # Assert
    assert result.status == "passed"
    assert result.exit_code == 0
    assert "hello" in result.output


@pytest.mark.skipif(shutil.which("echo") is None, reason="echo is not on PATH")
def test_run_echo_hook_receives_files() -> None:
    # Arrange — {files} substitution reaches the real command
    hook = HookDef.model_validate({"id": "say", "from": "system", "run": "echo {files}"})

    # Act
    result = run_hook(hook, [Path("x.py"), Path("y.py")])

    # Assert
    assert result.status == "passed"
    assert "x.py" in result.output
    assert "y.py" in result.output
