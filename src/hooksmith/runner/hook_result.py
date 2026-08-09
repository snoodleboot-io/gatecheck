"""HookResult — the outcome of running one hook (STY-0013 / GAT-14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

HookStatus = Literal["passed", "failed", "error"]


@dataclass(frozen=True)
class HookResult:
    """The result of executing a single hook.

    ``status`` is ``passed`` (exit 0), ``failed`` (non-zero exit), or ``error`` (the
    hook could not be resolved to an environment or the process could not be spawned).
    ``exit_code`` is ``None`` for an ``error`` that never reached a subprocess.
    """

    hook_id: str
    status: HookStatus
    exit_code: int | None
    output: str
    duration: float
