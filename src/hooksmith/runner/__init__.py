"""Public facade for hooksmith.runner (STY-0011)."""

from __future__ import annotations

from hooksmith.runner.changeset import Changeset, resolve_changeset, route_files
from hooksmith.runner.engine import run_plan
from hooksmith.runner.executor import run_hook
from hooksmith.runner.git_client import GitClient, GitError, SubprocessGitClient
from hooksmith.runner.hook_result import HookResult, HookStatus
from hooksmith.runner.plan import ExecutionPlan, SkippedHook, build_plan
from hooksmith.runner.plan_error import PlanError
from hooksmith.runner.process_runner import ProcessRunner, SubprocessProcessRunner
from hooksmith.runner.report import RunReport, build_report

__all__ = [
    "Changeset",
    "ExecutionPlan",
    "GitClient",
    "GitError",
    "HookResult",
    "HookStatus",
    "PlanError",
    "ProcessRunner",
    "RunReport",
    "SkippedHook",
    "SubprocessGitClient",
    "SubprocessProcessRunner",
    "build_plan",
    "build_report",
    "resolve_changeset",
    "route_files",
    "run_hook",
    "run_plan",
]
