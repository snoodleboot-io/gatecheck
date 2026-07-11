"""Public facade for gatecheck.runner (STY-0011)."""

from __future__ import annotations

from gatecheck.runner.changeset import Changeset, resolve_changeset
from gatecheck.runner.engine import run_plan
from gatecheck.runner.executor import run_hook
from gatecheck.runner.git_client import GitClient, GitError, SubprocessGitClient
from gatecheck.runner.hook_result import HookResult, HookStatus
from gatecheck.runner.plan import ExecutionPlan, SkippedHook, build_plan
from gatecheck.runner.plan_error import PlanError
from gatecheck.runner.process_runner import ProcessRunner, SubprocessProcessRunner

__all__ = [
    "Changeset",
    "ExecutionPlan",
    "GitClient",
    "GitError",
    "HookResult",
    "HookStatus",
    "PlanError",
    "ProcessRunner",
    "SkippedHook",
    "SubprocessGitClient",
    "SubprocessProcessRunner",
    "build_plan",
    "resolve_changeset",
    "run_hook",
    "run_plan",
]
