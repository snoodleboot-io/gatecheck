"""Unit tests for gatecheck.env.sync_environments (STY-0021 / GAT-20).

Hermetic — the EnvManager is a dependency-injected fake returning canned ``explain``
statuses; no real env resolution. Covers built (miss → resolve), cached (hit → no
resolve), ready (not-applicable), and error outcomes. AAA structure throughout.
"""

from __future__ import annotations

from pathlib import Path

from gatecheck.config import GatecheckConfig
from gatecheck.config.hook_def import HookDef
from gatecheck.env import CacheExplanation, EnvError, ResolvedEnv, sync_environments


class FakeEnvManager:
    """Returns a canned explain status per hook id; records resolve() calls."""

    def __init__(self, statuses: dict[str, str], errors: set[str] | None = None) -> None:
        self._statuses = statuses
        self._errors = errors or set()
        self.resolved: list[str] = []

    def explain(self, hook: HookDef) -> CacheExplanation:
        if hook.id in self._errors:
            raise EnvError(hook.id, "boom")
        status = self._statuses[hook.id]
        return CacheExplanation(
            hook_id=hook.id,
            source_kind="pypi",
            source_summary="pypi x==1 @ i",
            cache_key="k",
            key_material=("env-v1",),
            cache_dir="/c",
            status=status,
            reason="r",
        )

    def resolve(self, hook: HookDef) -> ResolvedEnv:
        self.resolved.append(hook.id)
        return ResolvedEnv(bin_dir=Path("/c/bin"), cache_key="k")


def _config(*ids: str) -> GatecheckConfig:
    hooks = [{"id": hid, "from": "system", "run": hid} for hid in ids]
    return GatecheckConfig.model_validate({"hook": hooks})


def test_miss_builds_and_reports_built() -> None:
    # Arrange
    config = _config("a")
    manager = FakeEnvManager({"a": "miss"})
    # Act
    outcomes = sync_environments(config, env_manager=manager)  # type: ignore[arg-type]
    # Assert — resolve was called to build it
    assert outcomes[0].status == "built"
    assert manager.resolved == ["a"]


def test_hit_reports_cached_without_resolving() -> None:
    # Arrange
    config = _config("a")
    manager = FakeEnvManager({"a": "hit"})
    # Act
    outcomes = sync_environments(config, env_manager=manager)  # type: ignore[arg-type]
    # Assert — no build
    assert outcomes[0].status == "cached"
    assert manager.resolved == []


def test_not_applicable_reports_ready() -> None:
    # Arrange
    config = _config("a")
    manager = FakeEnvManager({"a": "not-applicable"})
    # Act
    outcomes = sync_environments(config, env_manager=manager)  # type: ignore[arg-type]
    # Assert
    assert outcomes[0].status == "ready"
    assert manager.resolved == []


def test_resolution_error_reports_error() -> None:
    # Arrange
    config = _config("a")
    manager = FakeEnvManager({}, errors={"a"})
    # Act
    outcomes = sync_environments(config, env_manager=manager)  # type: ignore[arg-type]
    # Assert
    assert outcomes[0].status == "error"
    assert "boom" in outcomes[0].detail


def test_mixed_config_outcomes_in_order() -> None:
    # Arrange
    config = _config("a", "b", "c")
    manager = FakeEnvManager({"a": "miss", "b": "hit", "c": "not-applicable"})
    # Act
    outcomes = sync_environments(config, env_manager=manager)  # type: ignore[arg-type]
    # Assert
    assert [(o.hook_id, o.status) for o in outcomes] == [
        ("a", "built"),
        ("b", "cached"),
        ("c", "ready"),
    ]
    assert manager.resolved == ["a"]  # only the miss built
