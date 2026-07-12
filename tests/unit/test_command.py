"""Unit tests for gatecheck.command.tokenize (STY-0025 / GAT-27).

Hermetic — platform simulated via ``venv._is_windows`` (patching ``os.name`` would
break ``pathlib`` on POSIX). Covers POSIX splitting, Windows backslash preservation,
and the unbalanced-quote error. AAA throughout.
"""

from __future__ import annotations

import pytest

from gatecheck import venv
from gatecheck.command import tokenize


def test_posix_splits_and_consumes_backslashes(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(venv, "_is_windows", lambda: False)
    # Act
    tokens = tokenize("ruff check --fix")
    # Assert
    assert tokens == ["ruff", "check", "--fix"]


def test_windows_preserves_backslash_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(venv, "_is_windows", lambda: True)
    # Act — a Windows path must survive tokenization intact
    tokens = tokenize(r"C:\tools\ruff.exe check")
    # Assert
    assert tokens == [r"C:\tools\ruff.exe", "check"]


def test_windows_would_mangle_under_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange — POSIX mode eats the backslashes (the bug this fixes)
    monkeypatch.setattr(venv, "_is_windows", lambda: False)
    # Act
    tokens = tokenize(r"C:\tools\ruff.exe")
    # Assert — POSIX collapses the path; hence the platform switch
    assert tokens == ["C:toolsruff.exe"]


def test_unbalanced_quotes_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    # Arrange
    monkeypatch.setattr(venv, "_is_windows", lambda: False)
    # Act / Assert
    with pytest.raises(ValueError):
        tokenize('ruff "unterminated')
