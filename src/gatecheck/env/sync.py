"""Environment sync — pre-create/refresh each hook's environment (STY-0021 / GAT-20).

Walks a config's hooks and ensures every environment exists ahead of time, so the
first ``gatecheck run`` is fast. Uses ``EnvManager.explain`` to classify each hook
(hit / miss / not-applicable) and only ``resolve``s (builds) on a miss, so nothing
is built twice. Resolution failures become an ``error`` outcome rather than an
exception.
"""

from __future__ import annotations

from dataclasses import dataclass

from gatecheck.config import GatecheckConfig
from gatecheck.env.env_error import EnvError
from gatecheck.env.manager import EnvManager
from gatecheck.registry import RegistryError
from gatecheck.sources import SourceResolutionError, SourceSpecError

SyncStatus = str  # "built" | "cached" | "ready" | "error"

_SYNC_ERRORS = (EnvError, RegistryError, SourceResolutionError, SourceSpecError)


@dataclass(frozen=True)
class SyncOutcome:
    """The result of syncing one hook's environment."""

    hook_id: str
    status: SyncStatus
    detail: str


def sync_environments(
    config: GatecheckConfig, *, env_manager: EnvManager | None = None
) -> tuple[SyncOutcome, ...]:
    """Ensure every hook in ``config`` has its environment, returning per-hook outcomes.

    ``built`` = a uv venv was created; ``cached`` = one already existed; ``ready`` =
    a ``project`` / ``system`` binary that needs no environment; ``error`` = the
    environment could not be resolved (message in ``detail``).
    """
    manager = EnvManager(sources=config.sources) if env_manager is None else env_manager
    outcomes: list[SyncOutcome] = []
    for hook in config.hook:
        try:
            explanation = manager.explain(hook)
            if explanation.status == "miss":
                manager.resolve(hook)
                status: SyncStatus = "built"
            elif explanation.status == "hit":
                status = "cached"
            else:
                status = "ready"
            outcomes.append(SyncOutcome(hook.id, status, ""))
        except _SYNC_ERRORS as exc:
            outcomes.append(SyncOutcome(hook.id, "error", str(exc)))
    return tuple(outcomes)
