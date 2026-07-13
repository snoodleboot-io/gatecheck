"""Acceptance test for cache explainability — config → EnvManager.explain (STY-0009 / GAT-11).

Hermetic end-to-end: a real ``check.toml`` fixture is parsed with ``load_config`` and
its ``project`` hook is explained against a fake ``.venv/bin`` in ``tmp_path``. A
module-wide subprocess spy asserts explainability spawns nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from gatecheck.config import load_config
from gatecheck.env import EnvManager
from gatecheck.venv import bin_dir_name

_CONFIG = """
[[hook]]
id = "lint"
from = "project"
run = "ruff check"
"""


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("cache explainability must not spawn a subprocess")

    monkeypatch.setattr(subprocess, "run", _boom)
    monkeypatch.setattr(subprocess, "Popen", _boom)


def test_explain_project_hook_from_loaded_config(tmp_path: Path) -> None:
    # Arrange — a real check.toml + a fake project venv executable
    (tmp_path / "check.toml").write_text(_CONFIG, encoding="utf-8")
    exe = tmp_path / ".venv" / bin_dir_name() / "ruff"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    exe.chmod(0o755)

    config = load_config(tmp_path / "check.toml")
    manager = EnvManager(
        workspace_root=tmp_path, environ={"PATH": "/nonexistent"}, sources=config.sources
    )

    # Act
    ex = manager.explain(config.hook[0])

    # Assert
    assert ex.hook_id == "lint"
    assert ex.source_kind == "project"
    assert ex.status == "not-applicable"
    assert ex.cache_dir == str(exe.resolve().parent)
    assert len(ex.cache_key) == 64
