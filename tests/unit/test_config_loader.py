"""Unit tests for gatecheck.config.loader.load_config.

Implements STY-0001 / TSK-002 / TSK-004 test obligations.

Contract under test is locked by
`planning/build-plans/0001-architecture-sketch.md`:

- Section 4: `load_config(path: Path) -> GatecheckConfig`, synchronous,
  side-effect-free beyond opening `path` in binary mode.
- Section 5: errors propagate unwrapped (`FileNotFoundError`,
  `tomllib.TOMLDecodeError`, `pydantic.ValidationError`). No custom
  exception type is introduced in STY-0001.
- Section 6: every pydantic model uses
  `ConfigDict(extra="forbid", populate_by_name=True)`.
- Section 3.4: top-level defaults are `hook=[]`, `group={}`, `sources=None`.

These tests deliberately avoid mocks (`unittest.mock` is not imported);
the architect's contract calls for real filesystem reads via `tmp_path`.
The single str-vs-Path test documents that the type checker is the gate
(mypy is strict), not the runtime — `open()` accepts both.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tomllib
from pathlib import Path

import pydantic
import pytest

from gatecheck.config import GatecheckConfig, load_config

# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_config_returns_gatecheck_config(sample_check_toml: Path) -> None:
    # Arrange
    fixture_path = sample_check_toml

    # Act
    cfg = load_config(fixture_path)

    # Assert
    assert isinstance(cfg, GatecheckConfig)


def test_load_repo_check_toml() -> None:
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    repo_check_toml = repo_root / "check.toml"

    # Act
    cfg = load_config(repo_check_toml)

    # Assert
    assert len(cfg.hook) > 0


def test_load_config_is_synchronous() -> None:
    # Arrange / Act / Assert
    assert not asyncio.iscoroutinefunction(load_config)


# ---------------------------------------------------------------------------
# Round-trip / consistency
# ---------------------------------------------------------------------------


def test_load_config_idempotent(sample_check_toml: Path) -> None:
    # Arrange
    fixture_path = sample_check_toml

    # Act
    cfg1 = load_config(fixture_path)
    cfg2 = load_config(fixture_path)

    # Assert
    assert cfg1.model_dump() == cfg2.model_dump()


def test_load_config_matches_raw_tomllib(sample_check_toml: Path) -> None:
    # Arrange
    raw_dict = tomllib.loads(sample_check_toml.read_text())
    expected = GatecheckConfig.model_validate(raw_dict).model_dump()

    # Act
    actual = load_config(sample_check_toml).model_dump()

    # Assert
    assert actual == expected


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_load_config_raises_file_not_found_for_missing_path() -> None:
    # Arrange
    missing_path = Path("/nonexistent/check.toml")

    # Act & Assert
    with pytest.raises(FileNotFoundError):
        load_config(missing_path)


def test_load_config_rejects_oversized_file(tmp_path: Path) -> None:
    """Given a check.toml above the 1 MiB cap, When load_config runs, Then OSError
    is raised before tomllib is invoked (security hardening S3)."""
    # Arrange — 1 MiB + 1 byte of valid TOML padding (long comment)
    oversized = tmp_path / "oversized.toml"
    padding = "# " + ("a" * ((1 << 20) - 1)) + "\n"
    oversized.write_text(padding)

    # Act & Assert
    with pytest.raises(OSError, match="exceeds 1 MiB"):
        load_config(oversized)


@pytest.mark.skipif(sys.platform == "win32", reason="mkfifo unavailable on Windows")
def test_load_config_rejects_non_regular_file(tmp_path: Path) -> None:
    """Given a FIFO at the path, When load_config runs, Then OSError is raised
    before open() blocks on the pipe (security hardening S4)."""
    # Arrange
    fifo_path = tmp_path / "check.toml"
    os.mkfifo(fifo_path)

    # Act & Assert
    with pytest.raises(OSError, match="regular file"):
        load_config(fifo_path)


def test_load_config_raises_toml_decode_error_on_malformed_toml(
    tmp_path: Path,
) -> None:
    # Arrange
    bad_toml = tmp_path / "broken.toml"
    bad_toml.write_text("[malformed")

    # Act & Assert
    with pytest.raises(tomllib.TOMLDecodeError):
        load_config(bad_toml)


def test_load_config_raises_validation_error_on_missing_required_hook_id(
    tmp_path: Path,
) -> None:
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text('[[hook]]\nfrom = "pypi:ruff"\nrun  = "ruff check"\n')

    # Act & Assert
    with pytest.raises(pydantic.ValidationError) as exc_info:
        load_config(cfg_file)
    assert "id" in str(exc_info.value)


def test_load_config_raises_validation_error_on_unknown_key(
    tmp_path: Path,
) -> None:
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text(
        '[[hook]]\nid   = "ruff"\nfrom = "pypi:ruff"\nrun  = "ruff check"\nunknown-key = "x"\n'
    )

    # Act & Assert
    with pytest.raises(pydantic.ValidationError) as exc_info:
        load_config(cfg_file)
    message = str(exc_info.value)
    assert "unknown-key" in message or "unknown_key" in message


def test_load_config_raises_validation_error_on_wrong_type(
    tmp_path: Path,
) -> None:
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text(
        "[[hook]]\n"
        'id   = "ruff"\n'
        'from = "pypi:ruff"\n'
        'run  = "ruff check"\n'
        "\n"
        "[group.lint]\n"
        'hooks    = ["ruff"]\n'
        'parallel = "yes"\n'
    )

    # Act & Assert
    with pytest.raises(pydantic.ValidationError):
        load_config(cfg_file)


# ---------------------------------------------------------------------------
# Boundary / empty
# ---------------------------------------------------------------------------


def test_load_config_accepts_empty_toml(tmp_path: Path) -> None:
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text("")

    # Act
    cfg = load_config(cfg_file)

    # Assert
    assert cfg.hook == []
    assert cfg.group == {}
    assert cfg.sources is None


def test_load_config_accepts_only_sources_table(tmp_path: Path) -> None:
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text('[sources]\ndefault-registry = "https://pypi.org/simple"\n')

    # Act
    cfg = load_config(cfg_file)

    # Assert
    assert cfg.sources is not None
    assert cfg.hook == []
    assert cfg.group == {}


# ---------------------------------------------------------------------------
# Type-check guard
# ---------------------------------------------------------------------------


def test_load_config_rejects_str_path(sample_check_toml: Path) -> None:
    # Locked contract (architecture sketch §4): callers MUST pass a `pathlib.Path`.
    # Mypy is the primary gate. As of the S4 security hardening, the loader also
    # calls `path.stat()` before opening the file, which raises AttributeError on
    # a `str` argument — runtime now mirrors the static contract.

    # Arrange
    str_path = str(sample_check_toml)

    # Act & Assert
    with pytest.raises(AttributeError):
        load_config(str_path)  # type: ignore[arg-type]
