"""Unit tests for gatecheck.runner.SubprocessProcessRunner (STY-0013 / GAT-15).

Hermetic — ``subprocess.run`` is patched at the module boundary; no real process.
Asserts argv/env/cwd are forwarded and stdout+stderr are combined. AAA.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from gatecheck.runner import SubprocessProcessRunner
from gatecheck.runner import process_runner as process_runner_module


def test_forwards_argv_env_cwd_and_combines_output(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    captured: dict[str, object] = {}

    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        captured["argv"] = argv
        captured.update(kwargs)
        return SimpleNamespace(returncode=0, stdout="out", stderr="err")

    monkeypatch.setattr(process_runner_module.subprocess, "run", fake_run)

    # Act
    code, output = SubprocessProcessRunner().run(
        ["tool", "a.py"], env={"PATH": "/x"}, cwd=Path("/repo")
    )

    # Assert
    assert code == 0
    assert output == "outerr"  # stdout + stderr concatenated
    assert captured["argv"] == ["tool", "a.py"]
    assert captured["env"] == {"PATH": "/x"}
    assert captured["cwd"] == Path("/repo")


def test_os_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    def fake_run(argv: list[str], **kwargs: object) -> SimpleNamespace:
        raise FileNotFoundError("no tool")

    monkeypatch.setattr(process_runner_module.subprocess, "run", fake_run)

    # Act / Assert — OSError is not swallowed here (run_hook maps it to an error result)
    with pytest.raises(OSError, match="no tool"):
        SubprocessProcessRunner().run(["tool"], env={}, cwd=None)
