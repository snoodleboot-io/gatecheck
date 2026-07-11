"""Unit tests for gatecheck.runner.build_plan (STY-0012 / GAT-14).

Pure config → plan; hermetic (no filesystem, no git, injected ``environ``). Covers
all-vs-group selection, the unknown-group / unknown-hook / unknown-dep / cycle
``PlanError``s, the ``when`` skip matrix (with reasons), and the ``depends_on``
topological levelling (independent hooks share a level; a skipped dependency drops
its edge). AAA structure throughout.
"""

from __future__ import annotations

import pytest

from gatecheck.config import GatecheckConfig
from gatecheck.runner import ExecutionPlan, PlanError, build_plan


def _config(
    hooks: list[dict[str, object]], groups: dict[str, object] | None = None
) -> GatecheckConfig:
    data: dict[str, object] = {"hook": hooks}
    if groups is not None:
        data["group"] = groups
    return GatecheckConfig.model_validate(data)


def _hook(hook_id: str, **extra: object) -> dict[str, object]:
    return {"id": hook_id, "from": "system", "run": hook_id, **extra}


def _ids(plan: ExecutionPlan) -> list[list[str]]:
    return [[hook.id for hook in level] for level in plan.levels]


# ── selection ─────────────────────────────────────────────────────


def test_no_group_selects_all_hooks_in_order() -> None:
    # Arrange
    config = _config([_hook("a"), _hook("b")])
    # Act
    plan = build_plan(config, environ={})
    # Assert
    assert _ids(plan) == [["a", "b"]]
    assert plan.skipped == ()


def test_group_selects_named_hooks_in_group_order() -> None:
    # Arrange
    config = _config(
        [_hook("a"), _hook("b"), _hook("c")],
        groups={"lint": {"hooks": ["c", "a"]}},
    )
    # Act
    plan = build_plan(config, group="lint", environ={})
    # Assert — only c and a, in group order
    assert _ids(plan) == [["c", "a"]]


def test_unknown_group_raises() -> None:
    config = _config([_hook("a")])
    with pytest.raises(PlanError, match="unknown group 'nope'"):
        build_plan(config, group="nope", environ={})


def test_group_with_unknown_hook_raises() -> None:
    config = _config([_hook("a")], groups={"lint": {"hooks": ["a", "ghost"]}})
    with pytest.raises(PlanError, match="unknown hook 'ghost'"):
        build_plan(config, group="lint", environ={})


# ── depends_on DAG ────────────────────────────────────────────────


def test_depends_on_orders_into_levels() -> None:
    # Arrange — b and c depend on a; d depends on b
    config = _config(
        [
            _hook("a"),
            _hook("b", **{"depends-on": ["a"]}),
            _hook("c", **{"depends-on": ["a"]}),
            _hook("d", **{"depends-on": ["b"]}),
        ]
    )
    # Act
    plan = build_plan(config, environ={})
    # Assert — a alone, then b+c together, then d
    assert _ids(plan) == [["a"], ["b", "c"], ["d"]]


def test_unknown_dependency_raises() -> None:
    config = _config([_hook("a", **{"depends-on": ["ghost"]})])
    with pytest.raises(PlanError, match="depends on unknown hook 'ghost'"):
        build_plan(config, environ={})


def test_dependency_cycle_raises() -> None:
    config = _config([_hook("a", **{"depends-on": ["b"]}), _hook("b", **{"depends-on": ["a"]})])
    with pytest.raises(PlanError, match="cycle"):
        build_plan(config, environ={})


def test_skipped_dependency_edge_is_dropped() -> None:
    # Arrange — b depends on a, but a is skipped by when; b should still run (level 0)
    config = _config(
        [
            _hook("a", when={"env-not": "SKIP_A"}),
            _hook("b", **{"depends-on": ["a"]}),
        ]
    )
    # Act — SKIP_A set → a skipped
    plan = build_plan(config, environ={"SKIP_A": "1"})
    # Assert
    assert _ids(plan) == [["b"]]
    assert [s.hook_id for s in plan.skipped] == ["a"]


# ── when conditions ───────────────────────────────────────────────


def test_env_not_skips_with_reason() -> None:
    # Arrange
    config = _config([_hook("a", when={"env-not": "SKIP_A"})])
    # Act
    plan = build_plan(config, environ={"SKIP_A": "yes"})
    # Assert
    assert plan.levels == ()
    assert plan.skipped[0].hook_id == "a"
    assert "SKIP_A" in plan.skipped[0].reason


def test_on_ci_true_skipped_off_ci() -> None:
    # Arrange
    config = _config([_hook("a", when={"on-ci": True})])
    # Act — no CI vars
    plan = build_plan(config, environ={})
    # Assert
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "requires CI" in plan.skipped[0].reason


def test_on_ci_false_skipped_on_ci() -> None:
    # Arrange
    config = _config([_hook("a", when={"on-ci": False})])
    # Act — CI set
    plan = build_plan(config, environ={"CI": "true"})
    # Assert
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "disabled on CI" in plan.skipped[0].reason


def test_on_ci_true_runs_on_ci_via_github_actions() -> None:
    # Arrange
    config = _config([_hook("a", when={"on-ci": True})])
    # Act — GITHUB_ACTIONS counts as CI
    plan = build_plan(config, environ={"GITHUB_ACTIONS": "true"})
    # Assert — runs, nothing skipped
    assert _ids(plan) == [["a"]]
    assert plan.skipped == ()
