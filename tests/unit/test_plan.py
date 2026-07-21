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


# ── when: env (positive) ──────────────────────────────────────────


def test_env_runs_when_var_set() -> None:
    # Arrange — run only when DEPLOY is set
    config = _config([_hook("a", when={"env": "DEPLOY"})])
    # Act
    plan = build_plan(config, environ={"DEPLOY": "1"})
    # Assert
    assert _ids(plan) == [["a"]]


def test_env_skips_when_var_absent_with_reason() -> None:
    # Arrange
    config = _config([_hook("a", when={"env": "DEPLOY"})])
    # Act — DEPLOY unset
    plan = build_plan(config, environ={})
    # Assert
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "DEPLOY is not set" in plan.skipped[0].reason


# ── when: branch ──────────────────────────────────────────────────


def test_branch_runs_on_exact_match() -> None:
    config = _config([_hook("a", when={"branch": "main"})])
    plan = build_plan(config, environ={}, branch="main")
    assert _ids(plan) == [["a"]]


def test_branch_skips_off_branch_with_reason() -> None:
    config = _config([_hook("a", when={"branch": "main"})])
    plan = build_plan(config, environ={}, branch="feature/x")
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "not 'main'" in plan.skipped[0].reason


def test_branch_not_skips_on_exact_match() -> None:
    config = _config([_hook("a", when={"branch-not": "main"})])
    plan = build_plan(config, environ={}, branch="main")
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "branch-not" in plan.skipped[0].reason


def test_branch_not_is_glob_and_skips_release_branches() -> None:
    # Arrange — skip on any release/* branch
    config = _config([_hook("a", when={"branch-not": "release/*"})])
    # Act / Assert — a release branch is skipped
    off = build_plan(config, environ={}, branch="release/2.0")
    assert [s.hook_id for s in off.skipped] == ["a"]
    # Act / Assert — a non-release branch runs
    assert _ids(build_plan(config, environ={}, branch="main")) == [["a"]]


def test_branch_matches_glob_runs_and_skips() -> None:
    # Arrange
    config = _config([_hook("a", when={"branch-matches": "release/*"})])
    # Act / Assert — matching branch runs
    assert _ids(build_plan(config, environ={}, branch="release/1.2")) == [["a"]]
    # Act / Assert — non-matching branch skips
    off = build_plan(config, environ={}, branch="main")
    assert [s.hook_id for s in off.skipped] == ["a"]
    assert "does not match 'release/*'" in off.skipped[0].reason


def test_branch_condition_is_fail_open_without_branch() -> None:
    # Arrange — branch condition present but no branch context supplied
    config = _config([_hook("a", when={"branch": "main"})])
    # Act — branch defaults to None
    plan = build_plan(config, environ={})
    # Assert — hook runs (fail-open); the condition is not evaluated
    assert _ids(plan) == [["a"]]


# ── when: files-match ─────────────────────────────────────────────


def test_files_match_runs_when_a_file_matches() -> None:
    config = _config([_hook("a", when={"files-match": "*.py"})])
    plan = build_plan(config, environ={}, changed_files=["src/app.py", "README.md"])
    assert _ids(plan) == [["a"]]


def test_files_match_skips_when_no_file_matches() -> None:
    config = _config([_hook("a", when={"files-match": "*.py"})])
    plan = build_plan(config, environ={}, changed_files=["README.md"])
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "*.py" in plan.skipped[0].reason


def test_files_match_is_fail_open_without_changeset() -> None:
    # Arrange — no changed_files supplied
    config = _config([_hook("a", when={"files-match": "*.py"})])
    # Act
    plan = build_plan(config, environ={})
    # Assert — runs (fail-open)
    assert _ids(plan) == [["a"]]


def test_conditions_are_anded_first_failure_wins() -> None:
    # Arrange — env passes, but branch fails → skipped for the branch reason
    config = _config([_hook("a", when={"env": "DEPLOY", "branch": "main"})])
    # Act
    plan = build_plan(config, environ={"DEPLOY": "1"}, branch="dev")
    # Assert
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "not 'main'" in plan.skipped[0].reason


# ── no matching files (BUG-0002) ──────────────────────────────────


def test_hook_with_no_matching_files_is_skipped() -> None:
    """A file-consuming hook whose glob matches nothing must not run: with an empty
    {files} most tools scan the whole project, so a --fix hook would rewrite files
    the change never touched."""
    # Arrange
    config = _config([_hook("lint", files="*.py")])
    # Act — the changeset holds no Python files
    plan = build_plan(config, environ={}, changed_files=["README.md"])
    # Assert
    assert plan.levels == ()
    assert [s.hook_id for s in plan.skipped] == ["lint"]
    assert plan.skipped[0].reason == "no matching files"


def test_hook_runs_when_the_changeset_matches() -> None:
    # Arrange
    config = _config([_hook("lint", files="*.py")])
    # Act
    plan = build_plan(config, environ={}, changed_files=["src/app.py"])
    # Assert
    assert _ids(plan) == [["lint"]]
    assert plan.skipped == ()


def test_empty_changeset_skips_every_file_consuming_hook() -> None:
    # Arrange — nothing staged, the common `gatecheck run` case
    config = _config([_hook("a"), _hook("b", files="*.py")])
    # Act
    plan = build_plan(config, environ={}, changed_files=[])
    # Assert — both skipped; neither tool is handed an empty path list
    assert plan.levels == ()
    assert {s.hook_id for s in plan.skipped} == {"a", "b"}


def test_pass_files_false_hook_still_runs_with_no_files() -> None:
    # Arrange — a project-wide hook (mypy src/, cargo clippy) never wanted files
    config = _config([_hook("types", **{"pass-files": False})])
    # Act
    plan = build_plan(config, environ={}, changed_files=[])
    # Assert — exempt from the rule; pass-files = false is the escape hatch
    assert _ids(plan) == [["types"]]
    assert plan.skipped == ()


def test_exclude_emptying_the_set_skips_the_hook() -> None:
    # Arrange — the only matching file is excluded
    config = _config([_hook("lint", files="*.py", exclude="vendor/*")])
    # Act
    plan = build_plan(config, environ={}, changed_files=["vendor/x.py"])
    # Assert — routing and planning agree on the empty set
    assert [s.hook_id for s in plan.skipped] == ["lint"]


def test_no_matching_files_is_fail_open_without_a_changeset() -> None:
    # Arrange — changeset unknown (the run_affected / unit-test default)
    config = _config([_hook("lint", files="*.py")])
    # Act
    plan = build_plan(config, environ={})
    # Assert — runs rather than guessing
    assert _ids(plan) == [["lint"]]


def test_when_reason_wins_over_no_matching_files() -> None:
    # Arrange — both would skip; the explicit condition is the more useful reason
    config = _config([_hook("lint", files="*.py", when={"env-not": "SKIP"})])
    # Act
    plan = build_plan(config, environ={"SKIP": "1"}, changed_files=["README.md"])
    # Assert
    assert plan.skipped[0].reason == "env SKIP is set"


def test_dependent_of_a_file_skipped_hook_still_runs() -> None:
    # Arrange — b depends on a; a is skipped for want of files
    config = _config(
        [
            _hook("a", files="*.py"),
            _hook("b", **{"depends-on": ["a"], "pass-files": False}),
        ]
    )
    # Act
    plan = build_plan(config, environ={}, changed_files=["README.md"])
    # Assert — the edge drops, as with any other skip
    assert _ids(plan) == [["b"]]
    assert [s.hook_id for s in plan.skipped] == ["a"]


# ── when: requires-network (offline) ──────────────────────────────


def test_requires_network_skips_when_offline() -> None:
    # Arrange
    config = _config([_hook("a", when={"requires-network": True})])
    # Act — offline
    plan = build_plan(config, environ={"GATECHECK_OFFLINE": "1"})
    # Assert — skipped, not run, with a distinct network reason
    assert plan.levels == ()
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "offline" in plan.skipped[0].reason and "network" in plan.skipped[0].reason


def test_requires_network_runs_when_online() -> None:
    # Arrange
    config = _config([_hook("a", when={"requires-network": True})])
    # Act — no offline flag
    plan = build_plan(config, environ={})
    # Assert — runs; the marker is a no-op online
    assert _ids(plan) == [["a"]]
    assert plan.skipped == ()


def test_requires_network_reason_takes_precedence_offline() -> None:
    # Arrange — offline AND a branch that would also skip; network reason wins
    config = _config([_hook("a", when={"requires-network": True, "branch": "main"})])
    # Act
    plan = build_plan(config, environ={"GATECHECK_OFFLINE": "1"}, branch="dev")
    # Assert
    assert [s.hook_id for s in plan.skipped] == ["a"]
    assert "network" in plan.skipped[0].reason
