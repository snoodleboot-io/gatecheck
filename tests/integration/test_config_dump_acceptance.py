"""Acceptance tests for STY-0003 — Round-trip config dump.

This is the ATDD suite for STY-0003.  Tests are written before the
implementation exists (red-green-refactor): the module-level import of
``dump_config`` will produce an ``ImportError`` at collection time until
``gatecheck.config.dumper`` is created and ``dump_config`` is exported from
``gatecheck.config``.  That is the expected red state.

Once ``dump_config`` is implemented, all tests in this file must pass
without modification.

Contract under test:
    dump_config(config: GatecheckConfig, path: Path) -> None

    * Serialises ``config`` to a valid TOML file at ``path``.
    * Round-trip: load_config(p) → dump_config(result, p2) → load_config(p2)
      produces an object equal to the original.
    * ``[[hook]]`` entries use TOML array-of-tables syntax.
    * ``[group.<name>]`` entries use dotted-table syntax.
    * ``when = { … }`` is an inline table, not a bracketed sub-table.
    * ``None`` fields and default-valued fields are absent from the output.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from gatecheck.config import (
    GatecheckConfig,
    GroupDef,
    HookDef,
    dump_config,
    load_config,
)

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
FIXTURE_DIR: Path = Path(__file__).resolve().parents[1] / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_minimal_config_with_hooks(n: int) -> GatecheckConfig:
    """Return a GatecheckConfig with *n* minimal hooks and no other tables."""
    hooks = [
        HookDef.model_validate({"id": f"hook-{i}", "from": "project", "run": f"cmd-{i}"})
        for i in range(n)
    ]
    return GatecheckConfig(hook=hooks)


# ---------------------------------------------------------------------------
# Round-trip tests
# ---------------------------------------------------------------------------


def test_dump_and_reload_repo_check_toml(tmp_path: Path) -> None:
    """Given the repo's own check.toml,
    When it is loaded, dumped to a temporary path, and reloaded,
    Then the reloaded GatecheckConfig is equal to the original.

    Covers STY-0003 acceptance criterion: full round-trip on real-world config.
    """
    # Arrange
    source_path: Path = REPO_ROOT / "check.toml"
    output_path: Path = tmp_path / "check.toml"

    # Act
    original: GatecheckConfig = load_config(source_path)
    dump_config(original, output_path)
    reloaded: GatecheckConfig = load_config(output_path)

    # Assert
    assert reloaded == original


def test_dump_and_reload_sample_fixture(tmp_path: Path) -> None:
    """Given the tests/fixtures/check.toml.sample fixture,
    When it is loaded, dumped to a temporary path, and reloaded,
    Then the reloaded GatecheckConfig is equal to the original.

    Covers STY-0003 acceptance criterion: round-trip on the comprehensive
    fixture that exercises every field shape.
    """
    # Arrange
    source_path: Path = FIXTURE_DIR / "check.toml.sample"
    output_path: Path = tmp_path / "check.toml"

    # Act
    original: GatecheckConfig = load_config(source_path)
    dump_config(original, output_path)
    reloaded: GatecheckConfig = load_config(output_path)

    # Assert
    assert reloaded == original


# ---------------------------------------------------------------------------
# Valid TOML output
# ---------------------------------------------------------------------------


def test_dumped_toml_is_valid_toml(tmp_path: Path) -> None:
    """Given the tests/fixtures/check.toml.sample fixture,
    When it is loaded and dumped to a temporary path,
    Then the resulting file must parse as valid TOML without raising.

    Covers STY-0003 acceptance criterion: well-formed TOML output.
    """
    # Arrange
    source_path: Path = FIXTURE_DIR / "check.toml.sample"
    output_path: Path = tmp_path / "check.toml"
    original: GatecheckConfig = load_config(source_path)

    # Act
    dump_config(original, output_path)
    text: str = output_path.read_text(encoding="utf-8")

    # Assert — must not raise
    tomllib.loads(text)


# ---------------------------------------------------------------------------
# TOML structural syntax tests
# ---------------------------------------------------------------------------


def test_hook_sections_use_aot_syntax(tmp_path: Path) -> None:
    """Given a GatecheckConfig with three hooks,
    When dump_config writes it to disk,
    Then the output contains exactly three ``[[hook]]`` array-of-tables headers.

    Covers STY-0003 acceptance criterion: array-of-tables syntax for hooks.
    """
    # Arrange
    config: GatecheckConfig = _make_minimal_config_with_hooks(3)
    output_path: Path = tmp_path / "check.toml"

    # Act
    dump_config(config, output_path)
    text: str = output_path.read_text(encoding="utf-8")

    # Assert
    assert text.count("[[hook]]") == 3, (
        f"Expected 3 [[hook]] headers, got {text.count('[[hook]]')} in:\n{text}"
    )


def test_group_sections_use_dotted_header(tmp_path: Path) -> None:
    """Given a GatecheckConfig with groups named 'lint' and 'full',
    When dump_config writes it to disk,
    Then the output contains ``[group.lint]`` and ``[group.full]`` headers.

    Covers STY-0003 acceptance criterion: dotted-table syntax for groups.
    """
    # Arrange
    config: GatecheckConfig = GatecheckConfig(
        hook=[
            HookDef.model_validate({"id": "ruff", "from": "project", "run": "ruff check"}),
        ],
        group={
            "lint": GroupDef(hooks=["ruff"]),
            "full": GroupDef(hooks=["ruff"], parallel=True),
        },
    )
    output_path: Path = tmp_path / "check.toml"

    # Act
    dump_config(config, output_path)
    text: str = output_path.read_text(encoding="utf-8")

    # Assert
    assert "[group.lint]" in text, f"[group.lint] not found in:\n{text}"
    assert "[group.full]" in text, f"[group.full] not found in:\n{text}"


def test_when_is_inline_table(tmp_path: Path) -> None:
    """Given a GatecheckConfig whose hook has ``when = HookWhen(env_not='SKIP_MYPY')``,
    When dump_config writes it to disk,
    Then the output contains ``when = {`` (inline-table syntax) and does NOT
    contain a bracketed sub-table header such as ``[hook`` + ``.when]``.

    Covers STY-0003 acceptance criterion: inline-table serialisation of ``when``.
    """
    # Arrange
    hook: HookDef = HookDef.model_validate(
        {
            "id": "mypy",
            "from": "project",
            "run": "mypy src/",
            "pass-files": False,
            "when": {"env-not": "SKIP_MYPY"},
        }
    )
    config: GatecheckConfig = GatecheckConfig(hook=[hook])
    output_path: Path = tmp_path / "check.toml"

    # Act
    dump_config(config, output_path)
    text: str = output_path.read_text(encoding="utf-8")

    # Assert
    assert "when = {" in text, f"'when = {{' not found in:\n{text}"
    # The when sub-object must NOT be serialised as a bracketed sub-table.
    # A bracketed sub-table would look like [hook.when] or [[hook]]\n...\n[hook.when]
    assert ".when]" not in text, (
        f"'.when]' found in output — 'when' was serialised as a sub-table, not an inline table:\n{text}"
    )
