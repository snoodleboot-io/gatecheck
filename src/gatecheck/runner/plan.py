"""Execution-plan construction — hook selection + when + depends_on DAG (STY-0012 / GAT-14).

Turns a ``GatecheckConfig`` and a run context into a validated, dependency-ordered
``ExecutionPlan``: which hooks run (a named group or all), which are skipped by their
``when`` conditions (carried with a reason), and the parallelizable topological
levels the engine (STY-0014) consumes. Pure — no execution, no filesystem, no
subprocess.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from gatecheck.config import GatecheckConfig, HookDef
from gatecheck.runner.plan_error import PlanError

_CI_VARS = ("CI", "GITHUB_ACTIONS")


@dataclass(frozen=True)
class SkippedHook:
    """A selected hook excluded from execution by its ``when`` conditions."""

    hook_id: str
    reason: str


@dataclass(frozen=True)
class ExecutionPlan:
    """A dependency-ordered plan: parallelizable ``levels`` plus ``skipped`` hooks.

    Each entry in ``levels`` is a set of hooks with no unmet in-plan dependency — its
    members may run concurrently; later levels depend on earlier ones.
    """

    levels: tuple[tuple[HookDef, ...], ...]
    skipped: tuple[SkippedHook, ...]


def build_plan(
    config: GatecheckConfig,
    *,
    group: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> ExecutionPlan:
    """Build the execution plan for ``group`` (or all hooks) under ``environ``.

    Raises ``PlanError`` for an unknown group, a group/`depends_on` reference to an
    unknown hook, or a dependency cycle.
    """
    env = os.environ if environ is None else environ
    by_id = {hook.id: hook for hook in config.hook}

    selected = _select(config, group, by_id)
    is_ci = any(env.get(var) for var in _CI_VARS)

    running: list[HookDef] = []
    skipped: list[SkippedHook] = []
    for hook in selected:
        reason = _skip_reason(hook, env, is_ci=is_ci)
        if reason is None:
            running.append(hook)
        else:
            skipped.append(SkippedHook(hook_id=hook.id, reason=reason))

    _check_dependencies_exist(running, by_id)
    levels = _topological_levels(running)
    return ExecutionPlan(levels=levels, skipped=tuple(skipped))


def _select(
    config: GatecheckConfig, group: str | None, by_id: Mapping[str, HookDef]
) -> list[HookDef]:
    """Resolve the ordered, de-duplicated list of hooks a run selects."""
    if group is None:
        return list(config.hook)
    group_def = config.group.get(group)
    if group_def is None:
        raise PlanError(f"unknown group '{group}'")
    selected: list[HookDef] = []
    seen: set[str] = set()
    for hook_id in group_def.hooks:
        if hook_id in seen:
            continue
        hook = by_id.get(hook_id)
        if hook is None:
            raise PlanError(f"group '{group}' references unknown hook '{hook_id}'")
        selected.append(hook)
        seen.add(hook_id)
    return selected


def _skip_reason(hook: HookDef, environ: Mapping[str, str], *, is_ci: bool) -> str | None:
    """Return why ``hook`` is skipped by its ``when`` conditions, or ``None`` to run it."""
    when = hook.when
    if when is None:
        return None
    if when.env_not is not None and environ.get(when.env_not):
        return f"env {when.env_not} is set"
    if when.on_ci is True and not is_ci:
        return "requires CI (on-ci = true)"
    if when.on_ci is False and is_ci:
        return "disabled on CI (on-ci = false)"
    return None


def _check_dependencies_exist(hooks: list[HookDef], by_id: Mapping[str, HookDef]) -> None:
    """Raise ``PlanError`` if any ``depends_on`` names a hook absent from the config."""
    for hook in hooks:
        for dep in hook.depends_on:
            if dep not in by_id:
                raise PlanError(f"hook '{hook.id}' depends on unknown hook '{dep}'")


def _topological_levels(hooks: list[HookDef]) -> tuple[tuple[HookDef, ...], ...]:
    """Kahn topological sort into parallelizable levels; raise ``PlanError`` on a cycle.

    Edges to hooks that are not running (skipped / not selected) are dropped — a
    dependency that is not executing imposes no ordering. Declaration order is
    preserved within a level for deterministic output.
    """
    running = {hook.id: hook for hook in hooks}
    order = [hook.id for hook in hooks]
    deps = {hook.id: {dep for dep in hook.depends_on if dep in running} for hook in hooks}

    done: set[str] = set()
    remaining = set(running)
    levels: list[tuple[HookDef, ...]] = []
    while remaining:
        ready = [hid for hid in order if hid in remaining and deps[hid] <= done]
        if not ready:
            raise PlanError(f"dependency cycle among hooks: {sorted(remaining)}")
        levels.append(tuple(running[hid] for hid in ready))
        done.update(ready)
        remaining.difference_update(ready)
    return tuple(levels)
