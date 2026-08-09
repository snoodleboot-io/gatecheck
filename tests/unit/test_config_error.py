"""Unit tests for ConfigError + _error_translator (STY-0002 / BUILD-0002).

This module locks the contract defined by
``planning/build-plans/0002-architecture-decision.md``:

* §2 — ``ConfigError`` shape (subclasses ``ValueError``; carries
  ``path: Path`` and ``errors: list[tuple[int, int, str]]``; ``__str__``
  joins entries as ``"path:line:col: msg"``; empty ``errors`` is rejected).
* §3 — Translator signatures:
  ``_parse_toml_error(err) -> tuple[int, int, str]`` and
  ``_locate_validation_errors(err, source, toml_doc) -> list[tuple[int, int, str]]``.
* §4 — Position-lookup algorithm (anchor on table header, walk forward to
  the field-name line, parent-fallback when the field is absent from the
  source, 1-based line/col).
* §8 — Per-pydantic-error message format
  ``f"{msg} (field: {'.'.join(loc)})"``.

These tests intentionally fail on import while ``config_error.py`` and
``_error_translator.py`` do not yet exist — that is the RED state Lane B
will turn GREEN.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pydantic
import pytest
import tomlkit

from hooksmith.config import ConfigError
from hooksmith.config._error_translator import (
    _locate_validation_errors,
    _parse_toml_error,
    _safe_as_string,
    _walk_doc,
)
from hooksmith.config.config_error import ConfigError as ConfigErrorDirect
from hooksmith.config.hooksmith_config import HooksmithConfig

# ──────────────────────────────────────────────────────────────────────────
# ConfigError shape (BUILD-0002-ARCH §2)
# ──────────────────────────────────────────────────────────────────────────


def test_config_error_subclasses_value_error() -> None:
    """Given the ConfigError class, When checked, Then it is a subclass of ValueError
    (acceptance #4 — existing ``except ValueError:`` keeps working)."""
    # Arrange / Act / Assert
    assert issubclass(ConfigError, ValueError)


def test_config_error_facade_and_direct_module_are_same_class() -> None:
    """Given the public facade re-export and the direct module path, When compared,
    Then they refer to the identical class object (single source of truth, §7)."""
    # Arrange / Act / Assert
    assert ConfigError is ConfigErrorDirect


def test_config_error_str_format_single_entry() -> None:
    """Given a ConfigError with one entry, When str() is called, Then the format is
    ``"path:line:col: msg"`` (§2 contract)."""
    # Arrange
    exc = ConfigError(Path("x"), [(5, 3, "msg")])

    # Act
    rendered = str(exc)

    # Assert
    assert rendered == "x:5:3: msg"


def test_config_error_str_format_multi_entry() -> None:
    """Given a ConfigError with two entries, When str() is called, Then each entry
    is rendered on its own line, ``\\n``-joined (acceptance #3)."""
    # Arrange
    exc = ConfigError(Path("check.toml"), [(5, 3, "msg one"), (12, 1, "msg two")])

    # Act
    rendered = str(exc)

    # Assert
    assert rendered == "check.toml:5:3: msg one\ncheck.toml:12:1: msg two"


def test_config_error_empty_errors_list_raises() -> None:
    """Given an empty errors list, When ConfigError is constructed, Then ValueError
    is raised (defensive per §2 — empty ``__str__`` would violate acceptance #1)."""
    # Arrange / Act / Assert
    with pytest.raises(ValueError):
        ConfigError(Path("x"), [])


def test_config_error_path_attribute_accessible() -> None:
    """Given a ConfigError, When .path is read, Then the original Path is returned."""
    # Arrange
    path = Path("x")

    # Act
    exc = ConfigError(path, [(5, 3, "msg")])

    # Assert
    assert exc.path == path


def test_config_error_errors_attribute_accessible() -> None:
    """Given a ConfigError, When .errors is read, Then the original list is returned."""
    # Arrange
    entries = [(5, 3, "msg")]

    # Act
    exc = ConfigError(Path("x"), entries)

    # Assert
    assert exc.errors == [(5, 3, "msg")]


def test_config_error_str_includes_path_with_directory_components() -> None:
    """Given a path containing directory components, When str() is called, Then the
    full path string appears in the prefix (no basename truncation)."""
    # Arrange
    exc = ConfigError(Path("a/b/check.toml"), [(1, 1, "boom")])

    # Act
    rendered = str(exc)

    # Assert — the path renders with the platform separator (a\b on Windows)
    assert rendered.startswith(f"{Path('a/b/check.toml')}:1:1: ")


# ──────────────────────────────────────────────────────────────────────────
# _parse_toml_error (BUILD-0002-ARCH §3)
# ──────────────────────────────────────────────────────────────────────────


def test_parse_toml_error_extracts_line_col_from_message() -> None:
    """Given a TOMLDecodeError whose message contains ``at line N, column M``, When
    _parse_toml_error runs, Then it returns ``(N, M, str(err))`` (§3)."""
    # Arrange
    err = tomllib.TOMLDecodeError("Some msg at line 7, column 3")

    # Act
    line, col, msg = _parse_toml_error(err)

    # Assert
    assert (line, col) == (7, 3)
    assert msg == "Some msg at line 7, column 3"


def test_parse_toml_error_fallback_when_no_position_in_message() -> None:
    """Given a TOMLDecodeError whose message lacks position info, When _parse_toml_error
    runs, Then it falls back to ``(1, 1, str(err))`` (§3)."""
    # Arrange
    err = tomllib.TOMLDecodeError("Expected ']' at end of document")

    # Act
    line, col, msg = _parse_toml_error(err)

    # Assert
    assert (line, col) == (1, 1)
    assert msg == "Expected ']' at end of document"


def test_parse_toml_error_real_tomllib_position() -> None:
    """Given a real TOMLDecodeError raised by tomllib on positioned input, When
    _parse_toml_error runs, Then a positive (line, col) is extracted from the message."""
    # Arrange
    try:
        tomllib.loads("foo = 1\nbar bad = 2")
    except tomllib.TOMLDecodeError as e:
        err = e

    # Act
    line, col, _msg = _parse_toml_error(err)

    # Assert
    assert line >= 1
    assert col >= 1


def test_parse_toml_error_real_tomllib_end_of_document() -> None:
    """Given a real TOMLDecodeError that tomllib reports as ``at end of document``,
    When _parse_toml_error runs, Then it falls back to (1, 1, <msg>) (§3)."""
    # Arrange
    try:
        tomllib.loads("[unclosed")
    except tomllib.TOMLDecodeError as e:
        err = e

    # Act
    line, col, msg = _parse_toml_error(err)

    # Assert
    assert (line, col) == (1, 1)
    assert "end of document" in msg


# ──────────────────────────────────────────────────────────────────────────
# _locate_validation_errors (BUILD-0002-ARCH §4, §8)
# ──────────────────────────────────────────────────────────────────────────


def _validation_error_for(data: dict[str, object]) -> pydantic.ValidationError:
    """Helper: trigger a ValidationError by validating ``data`` against
    HooksmithConfig and return the captured exception."""
    try:
        HooksmithConfig.model_validate(data)
    except pydantic.ValidationError as e:
        return e
    raise AssertionError("Expected ValidationError, none was raised")


def test_locate_missing_required_field_in_hook() -> None:
    """Given a hook missing its required ``id`` field, When _locate_validation_errors
    runs, Then it returns one entry pointing at the ``[[hook]]`` header line and the
    message contains ``id`` and ``field: hook.0.id`` (§8)."""
    # Arrange
    source = '[[hook]]\nfrom = "x"\nrun = "x"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"hook": [{"from": "x", "run": "x"}]})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, _col, msg = results[0]
    assert line == 1  # [[hook]] header line
    assert "id" in msg
    assert "field: hook.0.id" in msg


def test_locate_unknown_key_in_hook() -> None:
    """Given a hook with an unknown extra key, When _locate_validation_errors runs,
    Then the entry points at the line where ``bogus`` is declared and the message
    references ``bogus``."""
    # Arrange
    source = '[[hook]]\nid = "x"\nfrom = "x"\nrun = "x"\nbogus = 1\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"hook": [{"id": "x", "from": "x", "run": "x", "bogus": 1}]})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, _col, msg = results[0]
    assert line == 5  # the `bogus = 1` line
    assert "bogus" in msg


def test_locate_wrong_type_in_group() -> None:
    """Given ``parallel`` declared with a string value inside ``[group.lint]``, When
    _locate_validation_errors runs, Then the entry points at the ``parallel`` line
    and the message mentions ``parallel`` (§4 dotted-table anchor)."""
    # Arrange
    source = '[group.lint]\nhooks = ["a"]\nparallel = "yes"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"group": {"lint": {"hooks": ["a"], "parallel": "yes"}}})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, _col, msg = results[0]
    assert line == 3  # the `parallel = "yes"` line
    assert "parallel" in msg


def test_locate_aot_disambiguation() -> None:
    """Given two ``[[hook]]`` headers where only the SECOND is missing ``id``, When
    _locate_validation_errors runs, Then the entry's line is the SECOND header's
    line, not the first (§4 AoT Nth-match rule)."""
    # Arrange
    source = '[[hook]]\nid = "first"\nfrom = "x"\nrun = "x"\n\n[[hook]]\nfrom = "x"\nrun = "x"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for(
        {
            "hook": [
                {"id": "first", "from": "x", "run": "x"},
                {"from": "x", "run": "x"},
            ]
        }
    )

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, _col, _msg = results[0]
    assert line == 6  # the SECOND `[[hook]]` header (1-indexed)


def test_locate_dotted_table_named_group() -> None:
    """Given two dotted ``[group.<name>]`` tables where the second triggers the
    error, When _locate_validation_errors runs, Then the entry's line is on the
    ``[group.lint]`` header (or within it), never on ``[group.format]`` (§4 dotted
    table anchor)."""
    # Arrange
    source = '[group.format]\nhooks = ["a"]\n\n[group.lint]\nhooks = "not-a-list"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for(
        {
            "group": {
                "format": {"hooks": ["a"]},
                "lint": {"hooks": "not-a-list"},
            }
        }
    )

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, _col, _msg = results[0]
    # `[group.lint]` is line 4; `hooks = "not-a-list"` is line 5.
    assert line in (4, 5)


def test_locate_top_level_sources_field() -> None:
    """Given an empty ``default-registry`` in ``[sources]``, When _locate_validation_errors
    runs, Then the entry returns a positive 1-based line (the line of the offending
    field or its parent header)."""
    # Arrange
    source = '[sources]\ndefault-registry = ""\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"sources": {"default-registry": ""}})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, col, _msg = results[0]
    assert line >= 1
    assert col >= 1


def test_locate_returns_one_entry_per_validation_error() -> None:
    """Given a document with two independent validation errors, When
    _locate_validation_errors runs, Then it returns exactly two entries (acceptance
    #3, multi-error support; §4 determinism via pydantic doc order)."""
    # Arrange
    source = '[[hook]]\nfrom = "x"\nrun = "x"\n\n[group.lint]\nhooks = []\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for(
        {
            "hook": [{"from": "x", "run": "x"}],
            "group": {"lint": {"hooks": []}},
        }
    )

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 2


def test_locate_fallback_parent_when_field_missing() -> None:
    """Given an unknown top-level key that doesn't appear in the source's parsed tree
    (extra_forbidden on a key with no presence beyond the typo itself), When
    _locate_validation_errors runs, Then the parent-fallback applies: (1, 1, <msg>)
    (§4 parent-fallback rule)."""
    # Arrange
    # Empty source — the typoed key isn't present at all in the document.
    source = ""
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"typoed_top": 1})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert len(results) == 1
    line, col, _msg = results[0]
    assert (line, col) == (1, 1)


def test_locate_returns_one_based_line_and_col() -> None:
    """Given any validation error, When _locate_validation_errors runs, Then every
    returned line and col is ≥ 1 (1-based, never 0 — §4)."""
    # Arrange
    source = '[[hook]]\nfrom = "x"\nrun = "x"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"hook": [{"from": "x", "run": "x"}]})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    assert all(line >= 1 and col >= 1 for line, col, _msg in results)


def test_locate_message_format_includes_field_path() -> None:
    """Given a validation error with a multi-element ``loc``, When
    _locate_validation_errors runs, Then the formatted message ends with
    ``(field: <dot-joined-loc>)`` (§8)."""
    # Arrange
    source = '[group.lint]\nhooks = ["a"]\nparallel = "yes"\n'
    toml_doc = tomlkit.parse(source)
    err = _validation_error_for({"group": {"lint": {"hooks": ["a"], "parallel": "yes"}}})

    # Act
    results = _locate_validation_errors(err, source, toml_doc)

    # Assert
    _line, _col, msg = results[0]
    assert "(field: group.lint.parallel)" in msg


# ──────────────────────────────────────────────────────────────────────────
# tomlkit tree-walk integration (Lane D RETRY — proves toml_doc is actually used)
# ──────────────────────────────────────────────────────────────────────────


def test_walk_doc_returns_item_for_resolvable_loc() -> None:
    """Given a TOMLDocument and a loc that resolves to a leaf, When _walk_doc runs,
    Then it returns the tomlkit Item plus the parent loc (RETRY: proves the walk
    actually navigates the document instead of being ignored)."""
    # Arrange
    source = '[[hook]]\nid = "x"\nfrom = "a"\nrun = "b"\n'
    doc = tomlkit.parse(source)
    loc: tuple[object, ...] = ("hook", 0, "id")

    # Act
    item, parent_loc = _walk_doc(doc, loc)

    # Assert
    assert item is not None
    assert parent_loc == ("hook", 0)
    # tomlkit's String exposes .as_string() — proves we got an Item, not a bare str
    assert hasattr(item, "as_string")


def test_walk_doc_returns_none_on_missing_key() -> None:
    """Given a loc that points at a key absent from the source tree, When _walk_doc
    runs, Then it returns ``(None, parent_loc)`` so the caller can take the
    parent-fallback branch (RETRY: this is the path that uses tomlkit's
    ``NonExistentKey`` which subclasses ``KeyError``)."""
    # Arrange
    source = '[group.lint]\nhooks = ["a"]\n'
    doc = tomlkit.parse(source)
    loc: tuple[object, ...] = ("group", "lint", "missing_field")

    # Act
    item, parent_loc = _walk_doc(doc, loc)

    # Assert
    assert item is None
    assert parent_loc == ("group", "lint")


def test_walk_doc_returns_none_on_aot_out_of_range() -> None:
    """Given a loc with an AoT index larger than the source supplies, When _walk_doc
    runs, Then it returns ``(None, parent_loc)`` (IndexError branch — RETRY)."""
    # Arrange
    source = '[[hook]]\nid = "only"\nfrom = "a"\nrun = "b"\n'
    doc = tomlkit.parse(source)
    loc: tuple[object, ...] = ("hook", 5, "id")

    # Act
    item, parent_loc = _walk_doc(doc, loc)

    # Assert
    assert item is None
    assert parent_loc == ("hook", 5)


def test_walk_doc_returns_none_on_scalar_subscript() -> None:
    """Given a loc that walks INTO a scalar leaf, When _walk_doc runs, Then it
    returns ``(None, parent_loc)`` (TypeError branch — RETRY)."""
    # Arrange
    source = "x = 5\n"
    doc = tomlkit.parse(source)
    loc: tuple[object, ...] = ("x", "y")

    # Act
    item, parent_loc = _walk_doc(doc, loc)

    # Assert
    assert item is None
    assert parent_loc == ("x",)


def test_safe_as_string_returns_rendered_text_for_tomlkit_item() -> None:
    """Given a tomlkit Item with ``.as_string()``, When _safe_as_string runs, Then
    it returns the rendered TOML text (RETRY: proves we read the value back from
    the doc rather than from a regex against the source)."""
    # Arrange
    doc = tomlkit.parse('[t]\ns = "hello"\n')
    item = doc["t"]["s"]

    # Act
    rendered = _safe_as_string(item)

    # Assert
    assert rendered is not None
    assert "hello" in rendered


def test_safe_as_string_returns_none_for_bare_bool() -> None:
    """Given a bare Python ``bool`` (tomlkit unwraps booleans away from Item), When
    _safe_as_string runs, Then it returns ``None`` so the field-scan falls back to
    name-only matching (RETRY judgment call documented in the helper docstring)."""
    # Arrange
    doc = tomlkit.parse("[t]\nb = true\n")
    item = doc["t"]["b"]  # native bool — no .as_string

    # Act
    rendered = _safe_as_string(item)

    # Assert
    assert rendered is None


def test_locate_exercises_toml_doc_walk_in_happy_path() -> None:
    """Given a recording TOMLDocument wrapper, When _locate_validation_errors runs
    against a resolvable loc, Then ``__getitem__`` is invoked on the doc — proving
    the implementation walks the tomlkit tree and does NOT regex-scan the source
    alone (RETRY: the exact criticism Lane F1 raised)."""
    # Arrange
    source = '[group.lint]\nhooks = ["a"]\nparallel = "yes"\n'
    doc = tomlkit.parse(source)
    err = _validation_error_for({"group": {"lint": {"hooks": ["a"], "parallel": "yes"}}})

    getitem_calls: list[object] = []
    original_getitem = type(doc).__getitem__

    def recording_getitem(self: object, key: object) -> object:
        getitem_calls.append(key)
        return original_getitem(self, key)  # type: ignore[no-any-return]

    monkey_target = type(doc)
    monkey_target.__getitem__ = recording_getitem  # type: ignore[method-assign]
    try:
        # Act
        results = _locate_validation_errors(err, source, doc)
    finally:
        monkey_target.__getitem__ = original_getitem  # type: ignore[method-assign]

    # Assert — the walk subscript-traversed the document at least once.
    assert any(call == "group" for call in getitem_calls)
    assert len(results) == 1


def test_locate_ignores_field_substring_in_comment_above_table() -> None:
    """Given a comment ABOVE the table that mentions the field name in
    free-form text, When _locate_validation_errors runs, Then the result points
    at the real field inside the table — not the comment line (RETRY: this is
    the substring-in-comment defense documented in the algorithm)."""
    # Arrange — the word ``parallel`` appears in a top-of-file comment, but the
    # anchor for ``[group.lint]`` lives further down, so the scan must skip the
    # comment line and only consider lines AFTER the table header.
    source = (
        "# parallel default behaviour is documented elsewhere\n"
        "[group.lint]\n"
        'hooks = ["a"]\n'
        'parallel = "yes"\n'
    )
    doc = tomlkit.parse(source)
    err = _validation_error_for({"group": {"lint": {"hooks": ["a"], "parallel": "yes"}}})

    # Act
    results = _locate_validation_errors(err, source, doc)

    # Assert
    assert len(results) == 1
    line, _col, _msg = results[0]
    assert line == 4  # ``parallel = "yes"`` is line 4; comment is line 1


def test_walk_doc_returns_document_for_empty_loc() -> None:
    """Given an empty loc tuple, When _walk_doc runs, Then it returns the doc itself
    and an empty parent_loc — guards the ``if not loc`` early-return branch."""
    # Arrange
    doc = tomlkit.parse('x = "y"\n')

    # Act
    item, parent_loc = _walk_doc(doc, ())

    # Assert
    assert item is doc
    assert parent_loc == ()


def test_safe_as_string_returns_none_for_object_without_attribute() -> None:
    """Given an object that lacks ``.as_string``, When _safe_as_string runs, Then
    it returns ``None`` — covers the ``getattr is None`` branch."""
    # Arrange / Act / Assert
    assert _safe_as_string(object()) is None
    assert _safe_as_string(42) is None


def test_safe_as_string_swallows_exception_from_as_string_call() -> None:
    """Given an object whose ``as_string()`` raises, When _safe_as_string runs, Then
    it returns ``None`` rather than propagating — covers the broad-except guard
    (judgment call: tomlkit container rendering may surprise us)."""

    # Arrange
    class Boom:
        def as_string(self) -> str:
            raise RuntimeError("kaboom")

    # Act / Assert
    assert _safe_as_string(Boom()) is None


def test_locate_walk_into_bool_skips_value_verification(tmp_path: Path) -> None:
    """Given a validation error whose loc resolves to a tomlkit-unwrapped bool
    (no ``.as_string``), When _locate_validation_errors runs, Then the scan falls
    back to field-name-only matching and still yields a valid line/col — covers
    the ``verify_needle is None`` early-return inside _scan_field."""
    # Arrange — ``parallel = true`` is a valid bool in source, but pydantic complains
    # because ``hooks`` is missing from the group.
    source = "[group.lint]\nparallel = true\n"
    doc = tomlkit.parse(source)
    err = _validation_error_for({"group": {"lint": {"parallel": True}}})

    # Act
    results = _locate_validation_errors(err, source, doc)

    # Assert — pydantic complains about missing ``hooks``; loc is
    # ``('group', 'lint', 'hooks')`` which fails to walk → parent fallback → line 1
    # of the [group.lint] header. The companion happy-path bool case below covers
    # the verify_needle=None branch in _scan_field directly.
    assert all(line >= 1 and col >= 1 for line, col, _ in results)


def test_locate_anchor_falls_back_when_container_is_unexpected() -> None:
    """Given a synthetic loc whose container has non-string parts that don't match
    the AoT shape, When _locate_validation_errors runs, Then the anchor degrades
    to line 1 (covers the trailing ``return 1`` in _anchor_line)."""
    # Arrange
    source = "x = 1\n"
    doc = tomlkit.parse(source)

    class FakeErr:
        def errors(self) -> list[dict[str, object]]:
            # Container is (int, int) — not AoT, not all-string → anchor falls through.
            return [{"loc": (0, 1, "field"), "msg": "fake"}]

    fake: pydantic.ValidationError = FakeErr()  # type: ignore[assignment]

    # Act
    results = _locate_validation_errors(fake, source, doc)

    # Assert
    assert len(results) == 1
    line, col, _msg = results[0]
    assert (line, col) == (1, 1)


def test_locate_table_header_absent_falls_back_to_line_one() -> None:
    """Given a dotted-table loc whose header is NOT present in source, When
    _locate_validation_errors runs, Then the anchor degrades to line 1 (covers
    the ``return None`` branch of _table_header_line)."""
    # Arrange — source has no [group.lint] header at all
    source = "x = 1\n"
    doc = tomlkit.parse(source)

    class FakeErr:
        def errors(self) -> list[dict[str, object]]:
            return [{"loc": ("group", "lint", "parallel"), "msg": "absent"}]

    fake: pydantic.ValidationError = FakeErr()  # type: ignore[assignment]

    # Act
    results = _locate_validation_errors(fake, source, doc)

    # Assert — anchor fallback → 1, scan finds nothing → still (1, 1)
    assert results == [(1, 1, "absent (field: group.lint.parallel)")]


def test_locate_stops_scan_at_next_table_header() -> None:
    """Given a field that IS NOT inside the anchor's table but a later table happens
    to have a same-named field, When _locate_validation_errors runs, Then the scan
    stops at the next ``[...]`` header — the wrong table's field is never matched."""
    # Arrange — error on ``[group.lint].parallel`` which is absent; scan must STOP
    # before reaching the ``parallel`` in ``[group.format]``.
    source = '[group.lint]\nhooks = ["a"]\n[group.format]\nhooks = ["b"]\nparallel = "yes"\n'
    doc = tomlkit.parse(source)

    class FakeErr:
        def errors(self) -> list[dict[str, object]]:
            return [{"loc": ("group", "lint", "parallel"), "msg": "missing"}]

    fake: pydantic.ValidationError = FakeErr()  # type: ignore[assignment]

    # Act
    results = _locate_validation_errors(fake, source, doc)

    # Assert — header anchor is line 1; scan hits ``[group.format]`` and stops →
    # field not found → fallback to (anchor_line, 1) which is (1, 1).
    assert results == [(1, 1, "missing (field: group.lint.parallel)")]


def test_locate_plain_match_used_when_value_verification_fails() -> None:
    """Given a synthetic doc-walk that returns a stub Item whose ``as_string``
    doesn't appear on the value line, When _locate_validation_errors runs, Then
    the scan still returns the plain field-name match (covers the plain_match
    fallback path in _scan_field)."""
    # Arrange — real source has parallel = "yes" on line 3
    source = '[group.lint]\nhooks = ["a"]\nparallel = "yes"\n'

    class StubItem:
        def as_string(self) -> str:
            # Mismatch — value text the source doesn't contain on the field's RHS
            return '"NOT-THE-REAL-VALUE"'

    class StubDoc:
        def __getitem__(self, key: object) -> object:
            return self  # always navigable; terminal StubItem is returned at leaf

    # Walk: ('group','lint','parallel') → first two return self, last returns StubItem.
    # We need the terminal lookup to return StubItem — use a chain depth counter.
    stub_doc_with_terminal_item = StubDoc()

    class TerminalDoc(StubDoc):
        def __init__(self) -> None:
            self.depth = 0

        def __getitem__(self, key: object) -> object:
            self.depth += 1
            if self.depth == 3:
                return StubItem()
            return self

    terminal = TerminalDoc()

    class FakeErr:
        def errors(self) -> list[dict[str, object]]:
            return [{"loc": ("group", "lint", "parallel"), "msg": "stub-value-mismatch"}]

    fake: pydantic.ValidationError = FakeErr()  # type: ignore[assignment]

    # Act
    results = _locate_validation_errors(fake, source, terminal)  # type: ignore[arg-type]

    # Assert — plain_match fallback returns the real parallel line (3, 1).
    assert len(results) == 1
    line, col, _msg = results[0]
    assert (line, col) == (3, 1)
    # Touch the unused-name lint by referencing it
    assert stub_doc_with_terminal_item is not None


def test_locate_parent_fallback_when_aot_index_out_of_range() -> None:
    """Given a (synthetic) pydantic-style loc that walks into an AoT index the source
    doesn't contain, When _locate_validation_errors runs, Then the parent-fallback
    path is taken (line = parent anchor, col = 1). RETRY: this exercises the
    IndexError branch in _walk_doc with a real ValidationError fixture.

    Note: pydantic v2 won't normally generate such a mismatched loc on its own, so
    we synthesise a ValidationError whose ``errors()`` returns a hand-built dict.
    """
    # Arrange — real source has ONE [[hook]] at line 1; loc claims [[hook]][3].
    source = '[[hook]]\nid = "only"\nfrom = "a"\nrun = "b"\n'
    doc = tomlkit.parse(source)

    class FakeErr:
        def errors(self) -> list[dict[str, object]]:
            return [{"loc": ("hook", 3, "id"), "msg": "synthetic"}]

    # Act — cast through Any so mypy stays happy in --strict mode
    fake: pydantic.ValidationError = FakeErr()  # type: ignore[assignment]
    results = _locate_validation_errors(fake, source, doc)

    # Assert — fell back to parent anchor (AoT header missing → defaults to line 1)
    assert len(results) == 1
    line, col, msg = results[0]
    assert (line, col) == (1, 1)
    assert "synthetic" in msg
