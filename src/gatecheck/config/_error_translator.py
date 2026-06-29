"""Translate tomllib + pydantic errors into ``(line, col, msg)`` triples (BUILD-0002-ARCH §3, §4, §8)."""

from __future__ import annotations

import re
import tomllib
from typing import TYPE_CHECKING, Any

import pydantic
import tomlkit

from gatecheck.sources import SourceSpecError, parse_source

if TYPE_CHECKING:
    from gatecheck.config.gatecheck_config import GatecheckConfig


def _parse_toml_error(err: tomllib.TOMLDecodeError) -> tuple[int, int, str]:
    """Extract ``(line, col, msg)`` from a ``TOMLDecodeError``; fall back to (1, 1, msg)."""
    text = str(err)
    match = re.search(r"at line (\d+), column (\d+)", text)
    if match is None:
        return (1, 1, text)
    return (int(match.group(1)), int(match.group(2)), text)


def _locate_validation_errors(
    err: pydantic.ValidationError,
    source: str,
    toml_doc: tomlkit.TOMLDocument,
) -> list[tuple[int, int, str]]:
    """Map each pydantic error to ``(line, col, formatted_msg)`` against the TOML source.

    Algorithm (BUILD-0002-ARCH §4):

    1. Walk ``toml_doc`` along the pydantic ``loc`` path. ``tomlkit.exceptions
       .NonExistentKey`` subclasses ``KeyError``; ``IndexError`` covers out-of-range
       AoT indices; ``TypeError`` covers subscripting a scalar leaf. Any of these
       means the field is not present in the source as that ``loc`` describes —
       fall back to the parent table's anchor line at column 1.
    2. When the walk succeeds, ``item.as_string()`` (where available) yields the
       rendered TOML text for the offending value. We use this text to *verify*
       the field-name line we matched in the source actually carries that value,
       which guards against the field-name appearing earlier as a substring of a
       comment or another value. (Bare ``bool`` leaves come back as native Python
       booleans from tomlkit and lack ``.as_string`` — those skip verification.)
    """
    results: list[tuple[int, int, str]] = []
    for err_dict in err.errors():
        loc: tuple[Any, ...] = tuple(err_dict["loc"])
        raw_msg = str(err_dict["msg"])
        formatted = f"{raw_msg} (field: {'.'.join(str(x) for x in loc)})"

        item, parent_loc = _walk_doc(toml_doc, loc)
        target_text = _safe_as_string(item) if item is not None else None
        anchor_line = _anchor_line(parent_loc, source)

        if item is None:
            # Parent-fallback: loc doesn't resolve in the source tree.
            line, col = anchor_line, 1
        else:
            field_name = str(loc[-1]) if loc else ""
            field_pos = _scan_field(source, anchor_line, field_name, target_text)
            line, col = field_pos if field_pos is not None else (anchor_line, 1)

        results.append((line, col, formatted))
    return results


def _locate_source_spec_errors(
    config: GatecheckConfig,
    source: str,
) -> list[tuple[int, int, str]]:
    """Return ``(line, col, msg)`` for each hook whose ``from_`` fails parse_source.

    Algorithm (BUILD-0004-ARCH §6): parse each validated hook's ``from_``; on
    ``SourceSpecError`` anchor the diagnostic at that hook's ``from`` key in
    ``source``. The validated ``config.hook`` list preserves source order, so the
    list index is the array-of-tables index. Falls back to ``(anchor, 1)`` if the
    field scan cannot pinpoint the key. ``UnsupportedSource`` results are valid and
    add no error.
    """
    results: list[tuple[int, int, str]] = []
    for index, hook in enumerate(config.hook):
        try:
            parse_source(hook.from_)
        except SourceSpecError as exc:
            anchor = _nth_aot_header_line(source, "hook", index)
            pos = _scan_field(source, anchor, "from", hook.from_)
            line, col = pos if pos is not None else (anchor, 1)
            msg = f"{exc} (hook: {hook.id})"
            results.append((line, col, msg))
    return results


def _walk_doc(toml_doc: tomlkit.TOMLDocument, loc: tuple[Any, ...]) -> tuple[Any, tuple[Any, ...]]:
    """Walk ``toml_doc`` along ``loc``; return (item-or-None, parent_loc).

    Catches ``KeyError`` (incl. tomlkit's ``NonExistentKey``), ``IndexError`` (AoT
    out-of-range), and ``TypeError`` (subscripting a scalar). On failure ``item``
    is ``None`` and ``parent_loc`` is ``loc[:-1]`` so the caller can anchor on the
    enclosing table header.
    """
    parent_loc = loc[:-1]
    if not loc:
        return (toml_doc, parent_loc)
    item: Any = toml_doc
    try:
        for key in loc:
            item = item[key]
    except (KeyError, IndexError, TypeError):
        return (None, parent_loc)
    return (item, parent_loc)


def _safe_as_string(item: Any) -> str | None:
    """Return ``item.as_string()`` if available; otherwise ``None``.

    tomlkit unwraps booleans into native ``bool`` (which lacks ``.as_string``), and
    similarly may unwrap other primitives in edge cases. Returning ``None`` here
    means the field-line scan won't use value-verification — that's fine: the
    field-name match alone suffices when verification text is unavailable.
    """
    as_string = getattr(item, "as_string", None)
    if as_string is None or not callable(as_string):
        return None
    try:
        return str(as_string())
    except Exception:  # tomlkit may raise on container as_string in rare cases.
        return None


def _anchor_line(container: tuple[Any, ...], source: str) -> int:
    """Return the 1-based source line for the table-header that contains ``container``.

    Empty container → line 1 (top-level scalar).
    ``(name, N)`` with int N → Nth ``[[name]]`` AoT header (0-indexed N).
    All-string container → ``[name1.name2....]`` dotted-table header.
    Anything else falls back to line 1.
    """
    if not container:
        return 1
    if len(container) == 2 and isinstance(container[0], str) and isinstance(container[1], int):
        return _nth_aot_header_line(source, container[0], container[1])
    if all(isinstance(part, str) for part in container):
        dotted = ".".join(str(part) for part in container)
        line = _table_header_line(source, dotted)
        return line if line is not None else 1
    return 1


def _nth_aot_header_line(source: str, name: str, index: int) -> int:
    """Return 1-based line of the Nth ``[[name]]`` header (0-indexed N); 1 if absent."""
    pattern = rf"^[ \t]*\[\[{re.escape(name)}\]\][ \t]*$"
    matches = list(re.finditer(pattern, source, flags=re.MULTILINE))
    if index < 0 or index >= len(matches):
        return 1
    return source.count("\n", 0, matches[index].start()) + 1


def _table_header_line(source: str, dotted: str) -> int | None:
    """Return 1-based line of ``[dotted]`` header in ``source``; None if absent."""
    pattern = rf"^[ \t]*\[{re.escape(dotted)}\][ \t]*$"
    match = re.search(pattern, source, flags=re.MULTILINE)
    if match is None:
        return None
    return source.count("\n", 0, match.start()) + 1


def _scan_field(
    source: str,
    anchor_line: int,
    field_name: str,
    target_text: str | None,
) -> tuple[int, int] | None:
    """Forward-scan from ``anchor_line`` for ``<field_name> =``; stop at next header.

    When ``target_text`` is supplied (from tomlkit's ``.as_string()``), prefer the
    first matching field-line whose right-hand-side contains ``target_text.strip()``.
    This is the tomlkit verification step: it disambiguates the case where the
    field-name appears earlier in a comment or another value. If no verified
    match is found we still accept the first plain field-name match.

    Returns 1-based ``(line, col)`` or ``None`` if the field is not present.
    """
    if not field_name:
        return None
    lines = source.splitlines()
    field_pattern = rf"^(\s*){re.escape(field_name)}\s*="
    header_pattern = r"^\s*\["
    verify_needle = target_text.strip() if target_text is not None else None
    plain_match: tuple[int, int] | None = None
    for idx in range(anchor_line, len(lines)):
        line_text = lines[idx]
        if re.match(header_pattern, line_text) is not None:
            break
        match = re.match(field_pattern, line_text)
        if match is None:
            continue
        line_col = (idx + 1, len(match.group(1)) + 1)
        if verify_needle is None:
            return line_col
        # Verification: does the RHS contain the tomlkit-rendered value text?
        rhs = line_text[match.end() :]
        if verify_needle in rhs:
            return line_col
        # Remember the first plain match in case no RHS verifies (e.g. multi-line
        # values where as_string() rendering spans lines).
        if plain_match is None:
            plain_match = line_col
    return plain_match
