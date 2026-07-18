"""Unit tests for gatecheck.offline.is_offline (STY-0034 / GAT-36)."""

from __future__ import annotations

import pytest

from gatecheck.offline import OFFLINE_ENV, is_offline


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1", True), ("true", True), ("anything", True), ("", False)],
)
def test_is_offline_reads_the_env_var(value: str, expected: bool) -> None:
    assert is_offline({OFFLINE_ENV: value}) is expected


def test_is_offline_false_when_absent() -> None:
    assert is_offline({}) is False


def test_is_offline_defaults_to_process_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setenv(OFFLINE_ENV, "1")
    # Act / Assert — no explicit environ → reads os.environ
    assert is_offline() is True
    monkeypatch.delenv(OFFLINE_ENV)
    assert is_offline() is False
