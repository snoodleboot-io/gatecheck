"""Unit tests for the SourceSpec.extra_registries schema field (STY-0006 / TSK-001).

Contract under test is LOCKED by
``planning/build-plans/0006-architecture-decision.md`` §7:

- ``extra_registries: dict[str, str]`` (TOML alias ``extra-registries``), default
  empty; both the Python attribute name and the hyphenated alias construct.
- a ``field_validator`` rejects an alias not matching ``[A-Za-z0-9_-]+`` and an
  empty URL value (raising ``ValueError`` -> surfaced as ``ValidationError`` /
  ``ConfigError``).
- round-trips through ``dump_config`` / ``load_config``: an empty map is omitted
  (default), a non-empty map dumps as an inline table and re-parses to the same
  ``dict[str, str]``.

This is a NEW file — ``tests/unit/test_config_schema.py`` is not modified. No mocks;
round-trip assertions operate on real filesystem writes via ``tmp_path``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from hooksmith.config import HooksmithConfig, SourceSpec, dump_config, load_config

# ---------------------------------------------------------------------------
# Schema — construction + default
# ---------------------------------------------------------------------------


def test_extra_registries_defaults_to_empty_dict() -> None:
    """Given no arguments, When SourceSpec() is built, Then extra_registries is {}."""
    # Arrange / Act
    spec = SourceSpec()

    # Assert
    assert spec.extra_registries == {}


def test_extra_registries_accepts_toml_alias_form() -> None:
    """Given the hyphenated ``extra-registries`` alias, When built, Then it populates
    the snake_case attribute as a dict[str, str]."""
    # Arrange
    payload = {"extra-registries": {"internal": "https://pkg.example.com/simple"}}

    # Act
    spec = SourceSpec(**payload)

    # Assert
    assert spec.extra_registries == {"internal": "https://pkg.example.com/simple"}


def test_extra_registries_accepts_python_attr_form() -> None:
    """Given the Python attribute name, When SourceSpec is built, Then the value stores."""
    # Arrange / Act
    spec = SourceSpec(extra_registries={"internal": "https://pkg.example.com/simple"})

    # Assert
    assert spec.extra_registries["internal"] == "https://pkg.example.com/simple"


def test_extra_registries_accepts_valid_alias_charset() -> None:
    """Given an alias using the full ``[A-Za-z0-9_-]+`` charset, When built, Then it
    is accepted (mirrors the parser's alias rule)."""
    # Arrange / Act
    spec = SourceSpec(extra_registries={"my_reg-1": "https://x.example/simple"})

    # Assert
    assert spec.extra_registries["my_reg-1"] == "https://x.example/simple"


# ---------------------------------------------------------------------------
# Schema — validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad_alias", ["bad.alias", "has space", "with/slash"])
def test_extra_registries_rejects_bad_alias(bad_alias: str) -> None:
    """Given an alias not matching [A-Za-z0-9_-]+, When built, Then ValidationError."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        SourceSpec(extra_registries={bad_alias: "https://x.example/simple"})


def test_extra_registries_rejects_empty_url() -> None:
    """Given an empty index URL, When SourceSpec is built, Then ValidationError."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError):
        SourceSpec(extra_registries={"internal": ""})


# ---------------------------------------------------------------------------
# Round-trip — dump_config / load_config
# ---------------------------------------------------------------------------


def test_extra_registries_round_trips_through_dump_and_load(tmp_path: Path) -> None:
    """Given a SourceSpec with extra_registries, When dumped then reloaded, Then the
    map survives and the whole config compares equal."""
    # Arrange
    cfg = HooksmithConfig(
        sources=SourceSpec(extra_registries={"internal": "https://pkg.example.com/simple"})
    )
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    reloaded = load_config(out)

    # Assert
    assert reloaded.sources is not None
    assert reloaded.sources.extra_registries == {"internal": "https://pkg.example.com/simple"}
    assert reloaded == cfg


def test_empty_extra_registries_omitted_from_dump(tmp_path: Path) -> None:
    """Given an empty extra_registries (the default), When dumped, Then the key is
    omitted from the output (§7: default -> excluded, round-trip unchanged)."""
    # Arrange
    cfg = HooksmithConfig(sources=SourceSpec(default_registry="https://pypi.org/simple"))
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "extra-registries" not in text


# ---------------------------------------------------------------------------
# load_config — a real check.toml exposes cfg.sources.extra_registries
# ---------------------------------------------------------------------------


def test_load_config_exposes_extra_registries_inline_table(tmp_path: Path) -> None:
    """Given a check.toml with an inline extra-registries table, When load_config runs,
    Then cfg.sources.extra_registries['internal'] is exposed."""
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text(
        '[sources]\nextra-registries = { internal = "https://pkg.example.com/simple" }\n',
        encoding="utf-8",
    )

    # Act
    result = load_config(cfg_file)

    # Assert
    assert result.sources is not None
    assert result.sources.extra_registries["internal"] == "https://pkg.example.com/simple"


def test_load_config_accepts_extra_registries_table_form(tmp_path: Path) -> None:
    """Given a check.toml with a [sources.extra-registries] table, When load_config
    runs, Then every alias -> URL entry is exposed."""
    # Arrange
    cfg_file = tmp_path / "check.toml"
    cfg_file.write_text(
        "[sources.extra-registries]\n"
        'internal = "https://pkg.example.com/simple"\n'
        'mirror = "https://mirror.example.com/simple"\n',
        encoding="utf-8",
    )

    # Act
    result = load_config(cfg_file)

    # Assert
    assert result.sources is not None
    assert result.sources.extra_registries == {
        "internal": "https://pkg.example.com/simple",
        "mirror": "https://mirror.example.com/simple",
    }
