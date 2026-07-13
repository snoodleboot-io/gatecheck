"""Acceptance tests for STY-0002 — Surface schema errors with file/line context.

These integration tests mirror the five user-facing acceptance criteria from
``planning/features/FEAT-0001-config-loader/stories/STY-0002-surface-error-context.md``
and the locked contract in
``planning/build-plans/0002-architecture-decision.md``.

Lane B (this file) writes the tests in the RED state — ``ConfigError`` does
not yet exist and ``load_config`` does not yet wrap raw exceptions. Lane D
will implement ``gatecheck.config.config_error`` and update the loader to
make these tests green. Per the two-layer test strategy, every test that
exercises ``load_config`` asserts both the wrapper layer (``ConfigError``
identity / format) and the underlying raw exception identity via
``exc.__cause__``.

Do not mock ``load_config``, ``ConfigError``, ``tomllib`` or ``pydantic``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pydantic
import pytest

from gatecheck.config import ConfigError, load_config

# Allow an optional Windows drive prefix (C:\...) before the path:line:col: form.
IDE_PREFIX_RE: re.Pattern[str] = re.compile(r"^(?:[A-Za-z]:)?[^:]+:\d+:\d+:\s+")


def test_malformed_toml_raises_config_error_with_ide_format(tmp_path: Path) -> None:
    """Given a check.toml whose TOML syntax is malformed,
    When load_config is invoked on it,
    Then it raises a ConfigError whose first line matches the IDE
    ``path:line:col: msg`` format and whose ``__cause__`` is the original
    ``tomllib.TOMLDecodeError`` (two-layer test strategy).

    Covers STY-0002 acceptance criterion 1.
    """
    # Arrange
    bad_toml: Path = tmp_path / "check.toml"
    bad_toml.write_text("[unclosed", encoding="utf-8")

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(bad_toml)

    # Assert
    first_line: str = str(exc_info.value).splitlines()[0]
    assert IDE_PREFIX_RE.match(first_line), (
        f"first line {first_line!r} does not match IDE error prefix"
    )
    assert isinstance(exc_info.value.__cause__, tomllib.TOMLDecodeError)


def test_missing_required_hook_id_raises_config_error_with_field_name(
    tmp_path: Path,
) -> None:
    """Given a check.toml where a [[hook]] entry omits the required ``id`` field,
    When load_config is invoked on it,
    Then it raises a ConfigError whose message mentions the field name ``id``
    and includes a ``:line:col:`` segment pointing at the offending entry,
    with ``__cause__`` set to the underlying ``pydantic.ValidationError``.

    Covers STY-0002 acceptance criterion 2.
    """
    # Arrange
    missing_id_toml: Path = tmp_path / "check.toml"
    missing_id_toml.write_text(
        '[[hook]]\nfrom = "x"\nrun = "x"\n',
        encoding="utf-8",
    )

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(missing_id_toml)

    # Assert
    rendered: str = str(exc_info.value)
    assert "id" in rendered, f"field name 'id' missing from {rendered!r}"
    assert re.search(r":\d+:\d+:", rendered), f"line:col segment missing from {rendered!r}"
    assert isinstance(exc_info.value.__cause__, pydantic.ValidationError)


def test_multiple_validation_errors_surface_one_per_line(tmp_path: Path) -> None:
    """Given a check.toml containing two independent schema violations
    (a [[hook]] entry missing ``id`` AND a [group.lint] table missing the
    required ``hooks`` field),
    When load_config is invoked on it,
    Then it raises a ConfigError whose ``__str__`` is a newline-joined
    list of at least two lines, with both offending field names present.

    Covers STY-0002 acceptance criterion 3.
    """
    # Arrange
    two_errors_toml: Path = tmp_path / "check.toml"
    two_errors_toml.write_text(
        '[[hook]]\nfrom = "pypi:ruff"\nrun = "ruff check"\n\n[group.lint]\nparallel = true\n',
        encoding="utf-8",
    )

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(two_errors_toml)

    # Assert
    rendered: str = str(exc_info.value)
    assert rendered.count("\n") >= 1, f"expected >= 2 lines, got {rendered!r}"
    assert "id" in rendered, f"missing 'id' field name in {rendered!r}"
    assert "hooks" in rendered, f"missing 'hooks' field name in {rendered!r}"


def test_config_error_is_value_error_subclass() -> None:
    """Given a freshly constructed ConfigError,
    When callers introspect its type and try to catch it as ValueError,
    Then it is recognised as both a ConfigError and a ValueError, preserving
    backward compatibility with existing ``except ValueError:`` handlers.

    Covers STY-0002 acceptance criterion 4.
    """
    # Arrange / Act
    exc: ConfigError = ConfigError(Path("/x/check.toml"), [(1, 1, "msg")])

    # Assert
    assert isinstance(exc, ConfigError)
    assert isinstance(exc, ValueError)
    try:
        raise exc
    except ValueError as caught:
        assert caught is exc
    else:  # pragma: no cover - defensive
        pytest.fail("ConfigError was not caught by `except ValueError`")


def test_public_facade_exports_config_error() -> None:
    """Given the gatecheck.config public facade,
    When ConfigError and load_config are imported from it,
    Then ConfigError is a class subclassing ValueError and load_config is
    callable, locking the BUILD-0002 §6 public API surface.

    Covers STY-0002 acceptance criterion 5.
    """
    # Arrange / Act
    from gatecheck.config import ConfigError as ImportedConfigError
    from gatecheck.config import load_config as imported_load_config

    # Assert
    assert isinstance(ImportedConfigError, type)
    assert issubclass(ImportedConfigError, ValueError)
    assert callable(imported_load_config)
