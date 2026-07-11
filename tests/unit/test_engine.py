"""Unit tests for gatecheck.runner.run_plan — the Rust-backed engine (STY-0014 / GAT-16).

Exercises the real ``gatecheck_core.run_waves`` scheduler, but with the environment
and subprocess behind dependency-injected fakes (no real env resolution, no real
process). Covers dependency-ordered execution, parallel waves, result ordering, and
wave-granular fail-fast. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

from gatecheck.config import GatecheckConfig
from gatecheck.config.hook_def import HookDef
from gatecheck.env import ResolvedEnv
from gatecheck.runner import HookResult, build_plan, run_plan


class FakeEnvManager:
    """Stub EnvManager: every hook resolves to the same bin dir."""

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        return ResolvedEnv(bin_dir=Path("/opt/tool/bin"), cache_key="k")


class FakeProcessRunner:
    """ProcessRunner that fails for argv[0] in ``fail_ids`` (else passes)."""

    def __init__(self, fail_ids: set[str] | None = None) -> None:
        self._fail_ids = fail_ids or set()

    def run(self, argv: list[str], *, env: object, cwd: object) -> tuple[int, str]:
        tool = argv[0]
        return (1, "boom") if tool in self._fail_ids else (0, "ok")


def _config(hooks: list[dict[str, object]]) -> GatecheckConfig:
    return GatecheckConfig.model_validate({"hook": hooks})


def _hook(hook_id: str, deps: list[str] | None = None) -> dict[str, object]:
    # run == id so the FakeProcessRunner can decide pass/fail by argv[0].
    data: dict[str, object] = {"id": hook_id, "from": "system", "run": hook_id}
    if deps:
        data["depends-on"] = deps
    return data


def _run(config: GatecheckConfig, **kwargs: object) -> tuple[HookResult, ...]:
    plan = build_plan(config, environ={})
    return run_plan(
        plan,
        {},
        env_manager=FakeEnvManager(),  # type: ignore[arg-type]
        **kwargs,  # type: ignore[arg-type]
    )


def test_runs_dependency_chain_in_order() -> None:
    # Arrange — a -> b -> c
    config = _config([_hook("a"), _hook("b", ["a"]), _hook("c", ["b"])])
    # Act
    results = _run(config, runner=FakeProcessRunner())
    # Assert
    assert [r.hook_id for r in results] == ["a", "b", "c"]
    assert all(r.status == "passed" for r in results)
    assert all(isinstance(r, HookResult) for r in results)


def test_runs_independent_hooks_in_one_wave() -> None:
    # Arrange — a, b independent
    config = _config([_hook("a"), _hook("b")])
    # Act
    results = _run(config, runner=FakeProcessRunner())
    # Assert — both ran (order is the wave's input order)
    assert {r.hook_id for r in results} == {"a", "b"}


def test_fail_fast_stops_later_waves() -> None:
    # Arrange — a fails; b depends on a (separate wave)
    config = _config([_hook("a"), _hook("b", ["a"])])
    # Act
    results = _run(config, runner=FakeProcessRunner(fail_ids={"a"}), fail_fast=True)
    # Assert — only a ran, and it failed; b was never launched
    assert [r.hook_id for r in results] == ["a"]
    assert results[0].status == "failed"


def test_without_fail_fast_everything_runs_despite_failure() -> None:
    # Arrange — a fails; b depends on a
    config = _config([_hook("a"), _hook("b", ["a"])])
    # Act
    results = _run(config, runner=FakeProcessRunner(fail_ids={"a"}), fail_fast=False)
    # Assert — both ran
    assert [r.hook_id for r in results] == ["a", "b"]
    assert results[0].status == "failed"
    assert results[1].status == "passed"
