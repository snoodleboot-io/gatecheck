"""Unit tests for the run command's ``_max_workers`` concurrency-cap mapping (STY-0030).

Pure — builds a ``HooksmithConfig`` and asserts the effective worker cap for the
all-hooks run vs a serial group vs a parallel group. See the engine tests
(``test_engine.py``) for the cap's runtime effect.
"""

from __future__ import annotations

from hooksmith.cli.commands.run import _max_workers
from hooksmith.config import HooksmithConfig


def _config(groups: dict[str, object]) -> HooksmithConfig:
    return HooksmithConfig.model_validate(
        {"hook": [{"id": "a", "from": "system", "run": "a"}], "group": groups}
    )


def test_all_hooks_run_is_unbounded() -> None:
    # Arrange
    config = _config({"lint": {"hooks": ["a"]}})
    # Act / Assert — no group selected → None (rayon global pool)
    assert _max_workers(config, None) is None


def test_serial_group_caps_at_one() -> None:
    # Arrange — parallel defaults to false
    config = _config({"lint": {"hooks": ["a"]}})
    # Act / Assert
    assert _max_workers(config, "lint") == 1


def test_parallel_group_uses_max_workers() -> None:
    # Arrange
    config = _config({"lint": {"hooks": ["a"], "parallel": True, "max-workers": 3}})
    # Act / Assert
    assert _max_workers(config, "lint") == 3


def test_parallel_group_defaults_to_four() -> None:
    # Arrange — parallel on, max-workers unset → documented default of 4
    config = _config({"lint": {"hooks": ["a"], "parallel": True}})
    # Act / Assert
    assert _max_workers(config, "lint") == 4


def test_unknown_group_is_unbounded() -> None:
    # Arrange
    config = _config({"lint": {"hooks": ["a"]}})
    # Act / Assert — a group that isn't defined falls back to None (planner errors elsewhere)
    assert _max_workers(config, "ghost") is None
