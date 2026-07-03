"""Acceptance tests for STY-0004 — bad hook `from` surfaces as ConfigError.

Mirrors AC-8 from
``planning/features/FEAT-0002-source-resolution/stories/STY-0004-parse-classify-source-specs.md``
and the LOCKED integration contract in
``planning/build-plans/0004-architecture-decision.md`` §6:

  After a successful ``GatecheckConfig.model_validate``, ``load_config`` parses
  each hook's ``from`` eagerly; a ``SourceSpecError`` is re-raised as a
  ``ConfigError`` whose first line matches ``^check\\.toml:\\d+:\\d+:`` and which
  names both the bad spec and the offending hook (``(hook: <id>)``).

A valid ``check.toml`` with assorted valid ``from`` values (including the
recognized-but-unsupported ``local:``/``git:``/``docker:`` schemes, which §6
says load cleanly) must NOT raise — this guards against false positives.

No mocks: ``load_config`` is exercised against real files written to
``tmp_path``, mirroring the STY-0001/STY-0002 acceptance style.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from gatecheck.config import ConfigError, load_config

IDE_PREFIX_RE: re.Pattern[str] = re.compile(r"^check\.toml:\d+:\d+:")


def _write_and_chdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    """Write ``check.toml`` into ``tmp_path``, chdir there, and return the
    *relative* path ``Path("check.toml")``.

    AC-8 requires the rendered ConfigError first line to begin with the literal
    ``check.toml:LINE:COL:``. ConfigError faithfully echoes whatever path it was
    given (unchanged STY-0002 behavior), so we must invoke ``load_config`` with a
    relative ``check.toml`` path — hence the chdir into ``tmp_path``.
    """
    cfg = tmp_path / "check.toml"
    cfg.write_text(body, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return Path("check.toml")


# ---------------------------------------------------------------------------
# AC-8 — bad `from` raises ConfigError with IDE-format location + bad spec
# ---------------------------------------------------------------------------


def test_bad_from_unknown_scheme_raises_config_error_with_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a check.toml whose hook `from` is an unknown scheme,
    When load_config runs,
    Then it raises ConfigError whose first line matches check.toml:LINE:COL:
    and names the bad spec.

    Covers STY-0004 AC-8.
    """
    # Arrange
    cfg = _write_and_chdir(
        tmp_path,
        monkeypatch,
        '[[hook]]\nid   = "lint"\nfrom = "bogus:thing"\nrun  = "lint"\n',
    )

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)

    # Assert
    first_line = str(exc_info.value).splitlines()[0]
    assert IDE_PREFIX_RE.match(first_line), (
        f"first line {first_line!r} does not match check.toml:line:col:"
    )
    assert "bogus:thing" in str(exc_info.value)
    assert "unknown source scheme 'bogus'" in str(exc_info.value)


def test_bad_from_empty_requirement_raises_config_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a check.toml whose hook `from = "pypi:"` has an empty requirement,
    When load_config runs,
    Then it raises ConfigError matching check.toml:LINE:COL: naming the spec.

    Covers STY-0004 AC-8 (second bad-spec variant).
    """
    # Arrange
    cfg = _write_and_chdir(
        tmp_path,
        monkeypatch,
        '[[hook]]\nid   = "lint"\nfrom = "pypi:"\nrun  = "lint"\n',
    )

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)

    # Assert
    first_line = str(exc_info.value).splitlines()[0]
    assert IDE_PREFIX_RE.match(first_line)
    assert "requirement must not be empty" in str(exc_info.value)


def test_config_error_line_points_at_offending_hook_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a check.toml where the SECOND hook has the bad `from`,
    When load_config runs,
    Then the ConfigError location line number points at that hook's `from` key.

    Covers STY-0004 AC-8 (line:col anchored at the offending `from`).
    """
    # Arrange — first hook valid; bad `from` is on line 8.
    body = (
        "[[hook]]\n"  # line 1
        'id   = "ruff"\n'  # line 2
        'from = "pypi:ruff"\n'  # line 3
        'run  = "ruff check"\n'  # line 4
        "\n"  # line 5
        "[[hook]]\n"  # line 6
        'id   = "lint"\n'  # line 7
        'from = "bogus:thing"\n'  # line 8  <-- offending
        'run  = "lint"\n'  # line 9
    )
    cfg = _write_and_chdir(tmp_path, monkeypatch, body)
    expected_line = 8

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)

    # Assert
    first_line = str(exc_info.value).splitlines()[0]
    match = re.match(r"check\.toml:(\d+):\d+:", first_line)
    assert match is not None, f"no location in {first_line!r}"
    assert int(match.group(1)) == expected_line, (
        f"expected location at line {expected_line}, got {first_line!r}"
    )
    assert "(hook: lint)" in str(exc_info.value)


def test_multiple_bad_from_specs_surface_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given a check.toml with two hooks each having a bad `from`,
    When load_config runs,
    Then the ConfigError reports both offending specs (one line each).

    Covers STY-0004 AC-8 + arch §6 "Multiple bad specs".
    """
    # Arrange
    body = (
        "[[hook]]\n"
        'id   = "a"\n'
        'from = "bogus:thing"\n'
        'run  = "a"\n'
        "\n"
        "[[hook]]\n"
        'id   = "b"\n'
        'from = "ruff"\n'
        'run  = "b"\n'
    )
    cfg = _write_and_chdir(tmp_path, monkeypatch, body)

    # Act
    with pytest.raises(ConfigError) as exc_info:
        load_config(cfg)

    # Assert
    rendered = str(exc_info.value)
    assert all(line.startswith("check.toml:") for line in rendered.splitlines()), (
        f"every error line should start with literal check.toml: in {rendered!r}"
    )
    assert "unknown source scheme 'bogus'" in rendered
    assert "expected one of: project, system" in rendered
    assert rendered.count("\n") >= 1, f"expected >= 2 lines, got {rendered!r}"


# ---------------------------------------------------------------------------
# False-positive guard — valid `from` values load cleanly
# ---------------------------------------------------------------------------


def test_valid_from_values_load_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Given a check.toml with assorted VALID `from` values,
    When load_config runs,
    Then no ConfigError is raised (guards against false positives).

    Covers STY-0004 AC-8 negative case + arch §6 (unsupported schemes are valid).
    """
    # Arrange — project, system, pypi:, pypi+alias:, and recognized-unsupported.
    body = (
        "[[hook]]\n"
        'id   = "ruff"\n'
        'from = "pypi:ruff>=0.4,<1"\n'
        'run  = "ruff check"\n'
        "\n"
        "[[hook]]\n"
        'id   = "internal"\n'
        'from = "pypi+internal:org-linter==2.1.0"\n'
        'run  = "org-linter"\n'
        "\n"
        "[[hook]]\n"
        'id        = "mypy"\n'
        'from      = "project"\n'
        'run       = "mypy"\n'
        "pass-files = false\n"
        "\n"
        "[[hook]]\n"
        'id        = "fmt"\n'
        'from      = "system"\n'
        'run       = "cargo fmt"\n'
        "pass-files = false\n"
        "\n"
        "[[hook]]\n"
        'id        = "local-lint"\n'
        'from      = "local:scripts/lint.py"\n'
        'run       = "lint"\n'
        "pass-files = false\n"
    )
    cfg = _write_and_chdir(tmp_path, monkeypatch, body)

    # Act
    result = load_config(cfg)

    # Assert
    assert [h.from_ for h in result.hook] == [
        "pypi:ruff>=0.4,<1",
        "pypi+internal:org-linter==2.1.0",
        "project",
        "system",
        "local:scripts/lint.py",
    ]


def test_repo_check_toml_from_values_all_parse(tmp_path: Path) -> None:
    """Given the repo's own check.toml (all valid `from` values),
    When load_config runs,
    Then it loads cleanly with no SourceSpecError-derived ConfigError.

    Covers STY-0004 AC-8 negative case against the real project config.
    """
    # Arrange
    repo_root = Path(__file__).resolve().parents[2]
    repo_check_toml = repo_root / "check.toml"

    # Act
    cfg = load_config(repo_check_toml)

    # Assert
    assert len(cfg.hook) > 0
