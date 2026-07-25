"""Parallel execution engine — drive an ExecutionPlan through the Rust core (STY-0014 / GAT-16).

Bridges the Python planner/executor and the native ``gatecheck_core.run_graph``
dynamic scheduler: it hands the Rust engine the dependency graph (the running hooks
plus their in-plan dependency edges) and a callback that runs one hook
(``run_hook``), and collects the results. Rust owns the dynamic (non-wave-barrier)
scheduling and fail-fast — a hook starts the moment its dependencies finish; Python
owns per-hook execution.
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
    max_workers: int | None = None,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    commit_msg_file: Path | None = None,
) -> tuple[HookResult, ...]:
    """Execute ``plan`` and return the ``HookResult``s in execution order.

    The plan's running hooks and their in-plan dependency edges become the graph for
    ``gatecheck_core.run_graph``: each hook starts as soon as its dependencies finish
    (dynamic scheduling, no wave barrier) and — when ``fail_fast`` — no not-yet-started
    hook launches after one returns non-passing. ``max_workers`` caps the number of
    hooks in flight at once (``1`` = serial); ``None`` runs unbounded on rayon's global
    pool. Each hook runs via ``run_hook`` with its routed files (``files_by_hook``);
    skipped hooks (``plan.skipped``) are not executed here.
    """
    running = [hook for level in plan.levels for hook in level]
    hooks = {hook.id: hook for hook in running}
    index_of = {hook.id: i for i, hook in enumerate(running)}
    results: dict[str, HookResult] = {}

    def execute(hook_id: str) -> int:
        result = run_hook(
            hooks[hook_id],
            files_by_hook.get(hook_id, ()),
            env_manager=env_manager,
            runner=runner,
            environ=environ,
            cwd=cwd,
            commit_msg_file=commit_msg_file,
        )
        results[hook_id] = result
        return _STATUS_CODE[result.status]

    nodes = [hook.id for hook in running]
    # Only edges to hooks that are actually running impose ordering; the planner has
    # already dropped edges to skipped / unselected hooks, so intersect defensively.
    deps = [[index_of[dep] for dep in hook.depends_on if dep in index_of] for hook in running]
    executed = core.run_graph(nodes, deps, execute, fail_fast, max_workers)
    return tuple(results[hook_id] for hook_id in executed)
