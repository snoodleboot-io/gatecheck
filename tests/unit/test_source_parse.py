"""Unit tests for gatecheck.sources.parse_source (STY-0004 / TSK-006).

Contract under test is LOCKED by
``planning/build-plans/0004-architecture-decision.md``:

- §3: frozen pydantic models ``PyPISource``, ``ProjectSource``,
  ``SystemSource``, ``UnsupportedSource``; ``ParsedSource`` plain union.
- §4: ``parse_source`` algorithm, match order, and the exact ``reason``
  message table (assertions here pin the LOCKED text so any code drift fails).
- §5: ``SourceSpecError(ValueError)`` with message
  ``invalid source spec '<spec>': <reason>``.
- §7: public import surface from ``gatecheck.sources``.

``parse_source`` is a pure function (§4 "Purity", AC-9): these tests use NO
mocks. AAA structure throughout. Assertions on error messages use
``pytest.raises(..., match=...)`` with the exact ``reason`` substrings from the
arch decision's message table, so a code-agent that diverges from the locked
wording is caught.
"""

from __future__ import annotations

import re

import pydantic
import pytest

from gatecheck.sources import (
    ParsedSource,
    ProjectSource,
    PyPISource,
    SourceSpecError,
    SystemSource,
    UnsupportedSource,
    parse_source,
)

# ---------------------------------------------------------------------------
# AC-1 / AC-2 / AC-3 — valid kinds
# ---------------------------------------------------------------------------


def test_parse_project_returns_project_source() -> None:
    # Arrange
    spec = "project"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == ProjectSource()
    assert result.kind == "project"


def test_parse_system_returns_system_source() -> None:
    # Arrange
    spec = "system"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == SystemSource()
    assert result.kind == "system"


def test_parse_pypi_returns_pypi_source_with_no_registry() -> None:
    # Arrange
    spec = "pypi:ruff"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == PyPISource(requirement="ruff", registry=None)
    assert result.kind == "pypi"


def test_parse_pypi_carries_multi_constraint_requirement_verbatim() -> None:
    # AC-2: requirement is carried verbatim, NOT PEP 508-validated.
    # Arrange
    spec = "pypi:ruff>=0.4,<1"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == PyPISource(requirement="ruff>=0.4,<1", registry=None)


def test_parse_pypi_with_alias_returns_pypi_source_with_registry() -> None:
    # AC-3
    # Arrange
    spec = "pypi+internal:org-linter==2.1.0"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == PyPISource(requirement="org-linter==2.1.0", registry="internal")
    assert result.registry == "internal"


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("project", ProjectSource()),
        ("system", SystemSource()),
        ("pypi:ruff", PyPISource(requirement="ruff", registry=None)),
        (
            "pypi:ruff>=0.4,<1",
            PyPISource(requirement="ruff>=0.4,<1", registry=None),
        ),
        (
            "pypi+internal:org-linter==2.1.0",
            PyPISource(requirement="org-linter==2.1.0", registry="internal"),
        ),
        (
            "pypi+my_reg-1:pkg",
            PyPISource(requirement="pkg", registry="my_reg-1"),
        ),
    ],
)
def test_parse_valid_specs_matrix(spec: str, expected: ParsedSource) -> None:
    # Arrange / Act
    result = parse_source(spec)

    # Assert
    assert result == expected


def test_parse_requirement_with_colon_keeps_remainder_after_first_colon() -> None:
    # §4 step 5 splits on len("pypi:"); the requirement may itself contain ':'.
    # Arrange
    spec = "pypi:pkg ; python_version >= '3.10'"

    # Act
    result = parse_source(spec)

    # Assert
    assert result == PyPISource(
        requirement="pkg ; python_version >= '3.10'", registry=None
    )


# ---------------------------------------------------------------------------
# Whitespace trimming (§4: s = spec.strip())
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("  project  ", ProjectSource()),
        ("\tsystem\n", SystemSource()),
        ("  pypi:ruff  ", PyPISource(requirement="ruff", registry=None)),
        (
            "  pypi+internal:org-linter==2.1.0  ",
            PyPISource(requirement="org-linter==2.1.0", registry="internal"),
        ),
    ],
)
def test_parse_trims_surrounding_whitespace(
    spec: str, expected: ParsedSource
) -> None:
    # Arrange / Act
    result = parse_source(spec)

    # Assert
    assert result == expected


# ---------------------------------------------------------------------------
# AC-4 — unsupported-but-recognized schemes do NOT raise
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "scheme"),
    [
        ("local:scripts/lint.py", "local"),
        ("git:https://x@v1", "git"),
        ("docker:img:tag", "docker"),
    ],
)
def test_parse_unsupported_scheme_returns_unsupported_source(
    spec: str, scheme: str
) -> None:
    # Arrange / Act
    result = parse_source(spec)

    # Assert
    assert result == UnsupportedSource(scheme=scheme)  # type: ignore[arg-type]
    assert result.kind == "unsupported"


@pytest.mark.parametrize(
    "spec",
    [
        "local:scripts/lint.py",
        "git:https://x@v1",
        "docker:img:tag",
    ],
)
def test_parse_unsupported_scheme_does_not_raise(spec: str) -> None:
    # AC-4: recognized-but-unsupported schemes must NOT raise.
    # Arrange / Act / Assert
    result = parse_source(spec)
    assert isinstance(result, UnsupportedSource)


# ---------------------------------------------------------------------------
# AC-5 / AC-6 — invalid specs raise SourceSpecError with the LOCKED reason text
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "reason"),
    [
        # empty / whitespace -> "spec is empty"
        ("", "spec is empty"),
        ("   ", "spec is empty"),
        ("\t\n", "spec is empty"),
        # pypi+ with no colon -> malformed
        ("pypi+internal", "expected 'pypi+<alias>:<requirement>'"),
        # empty alias
        ("pypi+:ruff", "registry alias must not be empty"),
        # bad alias characters (space)
        ("pypi+a b:ruff", "registry alias must match [A-Za-z0-9_-]+"),
        # bad alias characters (dot)
        ("pypi+bad.alias:ruff", "registry alias must match [A-Za-z0-9_-]+"),
        # empty requirement (pypi+)
        ("pypi+internal:", "requirement must not be empty"),
        # empty requirement (pypi)
        ("pypi:", "requirement must not be empty"),
        # unknown scheme
        ("bogus:thing", "unknown source scheme 'bogus'"),
        # project/system with payload land in unknown-scheme branch (§4 note)
        ("project:x", "unknown source scheme 'project'"),
        ("system:x", "unknown source scheme 'system'"),
        # bare word
        ("ruff", "expected one of: project, system, pypi:<req>, pypi+<alias>:<req>"),
    ],
)
def test_parse_invalid_spec_raises_with_locked_reason(
    spec: str, reason: str
) -> None:
    # AC-5: each invalid branch raises SourceSpecError.
    # Arrange / Act / Assert — match against the exact LOCKED reason substring.
    with pytest.raises(SourceSpecError, match=re.escape(reason)):
        parse_source(spec)


@pytest.mark.parametrize(
    ("spec", "reason"),
    [
        ("", "spec is empty"),
        ("pypi+:ruff", "registry alias must not be empty"),
        ("pypi:", "requirement must not be empty"),
        ("bogus:thing", "unknown source scheme 'bogus'"),
        ("ruff", "expected one of: project, system, pypi:<req>, pypi+<alias>:<req>"),
    ],
)
def test_parse_invalid_spec_full_message_format(spec: str, reason: str) -> None:
    # AC-6: message form is exactly "invalid source spec '<spec>': <reason>"
    # using the ORIGINAL (un-stripped) spec (§4 "Error construction").
    # Arrange / Act
    with pytest.raises(SourceSpecError) as exc_info:
        parse_source(spec)

    # Assert
    expected = f"invalid source spec '{spec}': {reason}"
    assert str(exc_info.value) == expected


def test_parse_invalid_spec_uses_unstripped_spec_in_message() -> None:
    # §4: the message echoes the original (un-stripped) spec verbatim.
    # Arrange
    spec = "  ruff  "

    # Act
    with pytest.raises(SourceSpecError) as exc_info:
        parse_source(spec)

    # Assert
    assert str(exc_info.value) == (
        "invalid source spec '  ruff  ': "
        "expected one of: project, system, pypi:<req>, pypi+<alias>:<req>"
    )


def test_source_spec_error_carries_structured_spec_and_reason() -> None:
    # §5: SourceSpecError exposes .spec and .reason attributes.
    # Arrange
    spec = "bogus:thing"

    # Act
    with pytest.raises(SourceSpecError) as exc_info:
        parse_source(spec)

    # Assert
    assert exc_info.value.spec == "bogus:thing"
    assert exc_info.value.reason == "unknown source scheme 'bogus'"


# ---------------------------------------------------------------------------
# AC-6 — SourceSpecError subclasses ValueError
# ---------------------------------------------------------------------------


def test_source_spec_error_is_value_error_subclass() -> None:
    # AC-6
    # Arrange / Act / Assert
    assert issubclass(SourceSpecError, ValueError)


def test_source_spec_error_caught_as_value_error() -> None:
    # AC-6: existing `except ValueError` handlers still catch it.
    # Arrange / Act
    with pytest.raises(ValueError) as exc_info:
        parse_source("ruff")

    # Assert
    assert isinstance(exc_info.value, SourceSpecError)


# ---------------------------------------------------------------------------
# AC-7 — the union is match-able on .kind without re-parsing the raw string
# ---------------------------------------------------------------------------


def test_parsed_result_is_matchable_on_kind() -> None:
    # AC-7: structural match over the discriminated union.
    # Arrange
    specs = ["project", "system", "pypi:ruff", "pypi+internal:pkg", "git:x"]

    # Act
    kinds: list[str] = []
    for spec in specs:
        match parse_source(spec):
            case ProjectSource():
                kinds.append("project")
            case SystemSource():
                kinds.append("system")
            case PyPISource(registry=None):
                kinds.append("pypi-default")
            case PyPISource():
                kinds.append("pypi-aliased")
            case UnsupportedSource(scheme=scheme):
                kinds.append(f"unsupported:{scheme}")

    # Assert
    assert kinds == [
        "project",
        "system",
        "pypi-default",
        "pypi-aliased",
        "unsupported:git",
    ]


def test_match_pypi_binds_requirement_and_registry() -> None:
    # AC-7: capture pattern binds parsed fields without touching the raw string.
    # Arrange
    result = parse_source("pypi+internal:org-linter==2.1.0")

    # Act
    matched: tuple[str, str | None] | None = None
    match result:
        case PyPISource(requirement=req, registry=reg):
            matched = (req, reg)

    # Assert
    assert matched == ("org-linter==2.1.0", "internal")


# ---------------------------------------------------------------------------
# Model immutability (§3 frozen=True, extra="forbid")
# ---------------------------------------------------------------------------


def test_pypi_source_is_frozen() -> None:
    # §3: models are frozen (immutable value objects).
    # Arrange
    source = PyPISource(requirement="ruff")

    # Act / Assert
    with pytest.raises(pydantic.ValidationError):  # frozen-instance mutation
        source.requirement = "black"  # type: ignore[misc]


def test_pypi_source_defaults_registry_to_none() -> None:
    # §3: registry defaults to None (default registry).
    # Arrange / Act
    source = PyPISource(requirement="ruff")

    # Assert
    assert source.registry is None


# ---------------------------------------------------------------------------
# AC-10 — public import contract
# ---------------------------------------------------------------------------


def test_public_import_surface() -> None:
    # AC-10: the locked seven-symbol facade is importable from gatecheck.sources.
    # Arrange / Act
    from gatecheck.sources import (
        ParsedSource as _ParsedSource,
    )
    from gatecheck.sources import (
        ProjectSource as _ProjectSource,
    )
    from gatecheck.sources import (
        PyPISource as _PyPISource,
    )
    from gatecheck.sources import (
        SourceSpecError as _SourceSpecError,
    )
    from gatecheck.sources import (
        SystemSource as _SystemSource,
    )
    from gatecheck.sources import (
        UnsupportedSource as _UnsupportedSource,
    )
    from gatecheck.sources import (
        parse_source as _parse_source,
    )

    # Assert
    assert callable(_parse_source)
    assert isinstance(_PyPISource, type)
    assert isinstance(_ProjectSource, type)
    assert isinstance(_SystemSource, type)
    assert isinstance(_UnsupportedSource, type)
    assert issubclass(_SourceSpecError, ValueError)
    assert _ParsedSource is not None
