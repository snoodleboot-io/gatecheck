"""Run reporting — summarize hook results into a report + exit code (STY-0015 / GAT-17).

Turns the executed ``HookResult``s and the ``ExecutionPlan`` into a ``RunReport``:
what passed / failed / errored, what was skipped by ``when``, and what never ran
(fail-fast blocked). Owns the human rendering and the process exit code so the CLI
stays a thin wrapper.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from gatecheck.runner.hook_result import HookResult
from gatecheck.runner.plan import ExecutionPlan, SkippedHook

_LABEL = {"passed": "ok  ", "failed": "FAIL", "error": "ERR "}


@dataclass(frozen=True)
class RunReport:
    """The outcome of a run: executed results, skipped hooks, and unrun hooks."""

    results: tuple[HookResult, ...]
    skipped: tuple[SkippedHook, ...]
    not_run: tuple[str, ...]

    @property
    def failed(self) -> int:
        """Number of hooks that failed or errored."""
        return sum(1 for result in self.results if result.status in ("failed", "error"))

    @property
    def exit_code(self) -> int:
        """0 when nothing failed or errored, else 1 (usable as a git-hook / CI gate)."""
        return 1 if self.failed else 0

    def render(self) -> str:
        """Render a human-readable per-hook report ending in a one-line summary."""
        lines: list[str] = []
        for result in self.results:
            lines.append(f"{_LABEL[result.status]}  {result.hook_id}  ({result.duration:.2f}s)")
            if result.status in ("failed", "error") and result.output.strip():
                lines.extend(f"      {line}" for line in result.output.rstrip().splitlines())
        for skip in self.skipped:
            lines.append(f"skip  {skip.hook_id}  ({skip.reason})")
        for hook_id in self.not_run:
            lines.append(f"----  {hook_id}  (not run)")
        lines.append("")
        lines.append(self._summary())
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict for ``--json`` output (mirrors ``CacheExplanation``)."""
        return {
            "results": [
                {
                    "hook_id": result.hook_id,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "duration": round(result.duration, 4),
                    "output": result.output,
                }
                for result in self.results
            ],
            "skipped": [{"hook_id": skip.hook_id, "reason": skip.reason} for skip in self.skipped],
            "not_run": list(self.not_run),
            "summary": {
                "passed": self._count("passed"),
                "failed": self._count("failed"),
                "error": self._count("error"),
                "skipped": len(self.skipped),
                "not_run": len(self.not_run),
            },
            "exit_code": self.exit_code,
        }

    def _count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)

    def _summary(self) -> str:
        passed = sum(1 for result in self.results if result.status == "passed")
        failed = sum(1 for result in self.results if result.status == "failed")
        errored = sum(1 for result in self.results if result.status == "error")
        parts = [f"{passed} passed"]
        if failed:
            parts.append(f"{failed} failed")
        if errored:
            parts.append(f"{errored} error")
        if self.skipped:
            parts.append(f"{len(self.skipped)} skipped")
        if self.not_run:
            parts.append(f"{len(self.not_run)} not run")
        return ", ".join(parts)


def build_report(plan: ExecutionPlan, results: Sequence[HookResult]) -> RunReport:
    """Assemble a ``RunReport`` from a plan and the results the engine produced.

    ``not_run`` is every hook the plan intended to run that has no result — i.e.
    hooks blocked by fail-fast — in plan order.
    """
    executed = {result.hook_id for result in results}
    planned = [hook.id for level in plan.levels for hook in level]
    not_run = tuple(hook_id for hook_id in planned if hook_id not in executed)
    return RunReport(results=tuple(results), skipped=plan.skipped, not_run=not_run)
