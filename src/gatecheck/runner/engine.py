"""Parallel execution engine — drive an ExecutionPlan through the Rust core (STY-0014 / GAT-16).

Bridges the Python planner/executor and the native ``gatecheck_core.run_waves``
scheduler: it flattens the plan's dependency levels into waves, hands the Rust
engine a callback that runs one hook (``run_hook``), and collects the results. Rust
owns the wave-parallel scheduling and fail-fast; Python owns per-hook execution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from gatecheck.core import core
from gatecheck.env import EnvManager
from gatecheck.runner.executor import run_hook
from gatecheck.runner.hook_result import HookResult
from gatecheck.runner.plan import ExecutionPlan
from gatecheck.runner.process_runner import ProcessRunner

# Status → exit-style code the Rust engine reads for its fail-fast decision.
_STATUS_CODE = {"passed": 0, "failed": 1, "error": 2}


def run_plan(
    plan: ExecutionPlan,
    files_by_hook: Mapping[str, Sequence[Path]],
    *,
    env_manager: EnvManager | None = None,
    runner: ProcessRunner | None = None,
    fail_fast: bool = False,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> tuple[HookResult, ...]:
    """Execute ``plan`` and return the ``HookResult``s in execution order.

    The plan's levels become waves for ``gatecheck_core.run_waves``: hooks in a wave
    run concurrently, later waves wait for earlier ones, and — when ``fail_fast`` —
    no wave starts after one that contained a non-passing hook. Each hook runs via
    ``run_hook`` with its routed files (``files_by_hook``); skipped hooks
    (``plan.skipped``) are not executed here.
    """
    hooks = {hook.id: hook for level in plan.levels for hook in level}
    results: dict[str, HookResult] = {}

    def execute(hook_id: str) -> int:
        result = run_hook(
            hooks[hook_id],
            files_by_hook.get(hook_id, ()),
            env_manager=env_manager,
            runner=runner,
            environ=environ,
            cwd=cwd,
        )
        results[hook_id] = result
        return _STATUS_CODE[result.status]

    waves = [[hook.id for hook in level] for level in plan.levels]
    executed = core.run_waves(waves, execute, fail_fast)
    return tuple(results[hook_id] for hook_id in executed)
