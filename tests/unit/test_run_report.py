"""Unit tests for hooksmith.runner.build_report / RunReport (STY-0015 / GAT-17).

Pure — constructed ``HookResult``s and a plan; no execution. Covers the exit code
(all-pass → 0, any failure/error → 1), the ``not_run`` computation (fail-fast
blocked), and the rendered summary. AAA structure throughout.
"""

from __future__ import annotations

import json

from hooksmith.config import HooksmithConfig
from hooksmith.runner import HookResult, build_plan, build_report


def _config(hooks: list[dict[str, object]]) -> HooksmithConfig:
    return HooksmithConfig.model_validate({"hook": hooks})


def _hook(
    hook_id: str, deps: list[str] | None = None, when: dict[str, object] | None = None
) -> dict[str, object]:
    data: dict[str, object] = {"id": hook_id, "from": "system", "run": hook_id}
    if deps:
        data["depends-on"] = deps
    if when:
        data["when"] = when
    return data


def _result(hook_id: str, status: str, output: str = "", exit_code: int | None = 0) -> HookResult:
    return HookResult(hook_id, status, exit_code, output, 0.1)  # type: ignore[arg-type]


def test_all_passed_exits_zero() -> None:
    # Arrange
    plan = build_plan(_config([_hook("a"), _hook("b")]), environ={})
    results = [_result("a", "passed"), _result("b", "passed")]
    # Act
    report = build_report(plan, results)
    # Assert
    assert report.exit_code == 0
    assert "2 passed" in report.render()


def test_a_failure_exits_one() -> None:
    # Arrange
    plan = build_plan(_config([_hook("a"), _hook("b")]), environ={})
    results = [_result("a", "passed"), _result("b", "failed", output="nope", exit_code=1)]
    # Act
    report = build_report(plan, results)
    # Assert
    assert report.exit_code == 1
    rendered = report.render()
    assert "FAIL  b" in rendered
    assert "nope" in rendered  # failing output is shown
    assert "1 passed, 1 failed" in rendered


def test_error_result_exits_one() -> None:
    # Arrange
    plan = build_plan(_config([_hook("a")]), environ={})
    results = [_result("a", "error", output="uv unavailable", exit_code=None)]
    # Act
    report = build_report(plan, results)
    # Assert
    assert report.exit_code == 1
    assert "ERR " in report.render()


def test_not_run_hooks_are_reported() -> None:
    # Arrange — plan has a and b (b depends on a); only a executed (fail-fast)
    plan = build_plan(_config([_hook("a"), _hook("b", ["a"])]), environ={})
    results = [_result("a", "failed", exit_code=1)]
    # Act
    report = build_report(plan, results)
    # Assert
    assert report.not_run == ("b",)
    rendered = report.render()
    assert "----  b  (not run)" in rendered
    assert "1 not run" in rendered


def test_skipped_hooks_are_reported() -> None:
    # Arrange — b is skipped by when; a runs
    plan = build_plan(
        _config([_hook("a"), _hook("b", when={"env-not": "SKIP_B"})]),
        environ={"SKIP_B": "1"},
    )
    results = [_result("a", "passed")]
    # Act
    report = build_report(plan, results)
    # Assert
    rendered = report.render()
    assert "skip  b" in rendered
    assert "1 passed, 1 skipped" in rendered
    assert report.exit_code == 0


def test_to_dict_covers_every_section_and_round_trips() -> None:
    # Arrange — a pass, a failure, a skip, and a not-run hook
    plan = build_plan(
        _config(
            [
                _hook("a"),
                _hook("b"),
                _hook("skipped", when={"env-not": "SKIP"}),
                _hook("later", ["b"]),
            ]
        ),
        environ={"SKIP": "1"},
    )
    results = [_result("a", "passed"), _result("b", "failed", output="boom", exit_code=1)]
    # Act
    payload = build_report(plan, results).to_dict()
    # Assert — serializable, and every section is represented
    assert json.loads(json.dumps(payload)) == payload
    assert [r["hook_id"] for r in payload["results"]] == ["a", "b"]
    assert payload["results"][1]["status"] == "failed"
    assert payload["results"][1]["exit_code"] == 1
    assert payload["results"][1]["output"] == "boom"
    assert payload["skipped"] == [
        {"hook_id": "skipped", "reason": "env SKIP is set"},
    ]
    assert payload["not_run"] == ["later"]
    assert payload["summary"] == {
        "passed": 1,
        "failed": 1,
        "error": 0,
        "skipped": 1,
        "not_run": 1,
    }
    assert payload["exit_code"] == 1


def test_to_dict_exit_code_zero_when_all_pass() -> None:
    # Arrange
    plan = build_plan(_config([_hook("a")]), environ={})
    # Act
    payload = build_report(plan, [_result("a", "passed")]).to_dict()
    # Assert
    assert payload["exit_code"] == 0
    assert payload["summary"]["passed"] == 1


def test_network_skip_is_surfaced_and_not_a_failure() -> None:
    # Arrange — a requires network but the run is offline → skipped, not failed
    plan = build_plan(
        _config([_hook("net", when={"requires-network": True})]),
        environ={"HOOKSMITH_OFFLINE": "1"},
    )
    # Act
    report = build_report(plan, [])
    # Assert — the distinct reason is shown; exit code stays 0
    rendered = report.render()
    assert "skip  net" in rendered
    assert "offline" in rendered and "network" in rendered
    assert report.exit_code == 0
