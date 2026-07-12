"""Unit tests for gatecheck.install.install_hooks (STY-0022 / GAT-21).

Hermetic — the hooks directory is a ``tmp_path`` behind a fake ``HooksLocator``; no
real repo. Covers event→hook mapping, grouping several groups into one hook script,
the executable bit + script contents, and the marker-guarded overwrite vs.
skip-unmanaged behavior. AAA structure throughout.
"""

from __future__ import annotations

import os
from pathlib import Path

from gatecheck.config import GatecheckConfig
from gatecheck.install import has_on_event_groups, install_hooks


class FakeLocator:
    """Returns a fixed hooks directory."""

    def __init__(self, hooks_dir: Path) -> None:
        self._hooks_dir = hooks_dir

    def hooks_dir(self) -> Path:
        return self._hooks_dir


def _config(
    groups: dict[str, dict[str, object]], hooks: list[str] | None = None
) -> GatecheckConfig:
    hook_ids = hooks or ["a", "b"]
    data = {
        "hook": [{"id": h, "from": "system", "run": h} for h in hook_ids],
        "group": groups,
    }
    return GatecheckConfig.model_validate(data)


def test_installs_pre_commit_for_commit_event(tmp_path: Path) -> None:
    # Arrange
    config = _config({"lint": {"hooks": ["a"], "on-event": "commit"}})
    # Act
    outcomes = install_hooks(config, locator=FakeLocator(tmp_path))
    # Assert
    assert [(o.git_hook, o.status) for o in outcomes] == [("pre-commit", "installed")]
    script = tmp_path / "pre-commit"
    assert script.exists()
    assert "gatecheck run lint" in script.read_text(encoding="utf-8")
    assert os.access(script, os.X_OK)


def test_push_event_maps_to_pre_push(tmp_path: Path) -> None:
    # Arrange
    config = _config({"tests": {"hooks": ["a"], "on-event": "push"}})
    # Act
    install_hooks(config, locator=FakeLocator(tmp_path))
    # Assert
    assert (tmp_path / "pre-push").exists()


def test_groups_sharing_an_event_share_one_hook(tmp_path: Path) -> None:
    # Arrange — two groups both on commit
    config = _config(
        {
            "lint": {"hooks": ["a"], "on-event": "commit"},
            "fmt": {"hooks": ["b"], "on-event": "commit"},
        }
    )
    # Act
    outcomes = install_hooks(config, locator=FakeLocator(tmp_path))
    # Assert — one pre-commit hook running both groups in order
    assert len(outcomes) == 1
    script = (tmp_path / "pre-commit").read_text(encoding="utf-8")
    assert "gatecheck run lint" in script
    assert "gatecheck run fmt" in script


def test_reinstall_overwrites_managed_hook(tmp_path: Path) -> None:
    # Arrange — install once, then again
    config = _config({"lint": {"hooks": ["a"], "on-event": "commit"}})
    install_hooks(config, locator=FakeLocator(tmp_path))
    # Act
    outcomes = install_hooks(config, locator=FakeLocator(tmp_path))
    # Assert — managed hook is overwritten, not skipped
    assert outcomes[0].status == "installed"


def test_unmanaged_existing_hook_is_skipped(tmp_path: Path) -> None:
    # Arrange — a pre-existing hook without the marker
    existing = tmp_path / "pre-commit"
    existing.write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
    config = _config({"lint": {"hooks": ["a"], "on-event": "commit"}})
    # Act
    outcomes = install_hooks(config, locator=FakeLocator(tmp_path))
    # Assert — not clobbered
    assert outcomes[0].status == "skipped"
    assert existing.read_text(encoding="utf-8") == "#!/bin/sh\necho mine\n"


def test_groups_without_on_event_install_nothing(tmp_path: Path) -> None:
    # Arrange
    config = _config({"lint": {"hooks": ["a"]}})  # no on-event
    # Assert
    assert has_on_event_groups(config) is False
    assert install_hooks(config, locator=FakeLocator(tmp_path)) == ()
