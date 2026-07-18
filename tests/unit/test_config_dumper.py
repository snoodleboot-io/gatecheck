"""Unit tests for gatecheck.config.dumper.dump_config (STY-0003 / BUILD-0003).

These tests are written in the RED state — dump_config does not yet exist.
Every test is expected to fail with ImportError or AttributeError until
the implementation is provided.

Contract under test (BUILD-0003-ARCH):
- dump_config(config: GatecheckConfig, path: Path) -> None
- Writes valid TOML to ``path``
- ``[[hook]]`` is a TOML array-of-tables; ``[group.<name>]`` is a dotted table;
  ``when`` is an inline table.
- ``None`` fields are omitted from the output.
- Fields at their default value are omitted from the output.
- ``from_`` on HookDef serialises as the TOML key ``from`` (not ``from_``).
- Round-trip: load_config(dump_path) == load_config(original_path).
- Raises IsADirectoryError or OSError when ``path`` is a directory.

No mocks are used; all assertions operate on real filesystem writes via
``tmp_path`` or the bundled ``sample_check_toml`` fixture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from gatecheck.config import GatecheckConfig, GroupDef, HookDef, SourceSpec, load_config
from gatecheck.config.hook_def import HookWhen

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_hook(
    hook_id: str = "lint", from_: str = "pypi:ruff", run: str = "ruff check"
) -> HookDef:
    """Return a minimal valid HookDef."""
    return HookDef(id=hook_id, **{"from": from_, "run": run})


# ---------------------------------------------------------------------------
# Smoke / happy path
# ---------------------------------------------------------------------------


def test_dump_creates_file(tmp_path: Path) -> None:
    """Given a minimal GatecheckConfig, When dump_config runs, Then the output
    file exists on disk."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig()
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)

    # Assert
    assert out.exists()


def test_dump_creates_regular_file(tmp_path: Path) -> None:
    """Given a minimal GatecheckConfig, When dump_config runs, Then the output
    path is a regular file (not a directory or symlink)."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig()
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)

    # Assert
    assert out.is_file()


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_dump_empty_config_round_trips(tmp_path: Path) -> None:
    """Given a default GatecheckConfig(), When dumped then reloaded, Then the
    reloaded config equals the original."""
    # Arrange
    from gatecheck.config import dump_config

    cfg1 = GatecheckConfig()
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg1, out)
    cfg2 = load_config(out)

    # Assert
    assert cfg1 == cfg2


def test_dump_sample_fixture_round_trips(sample_check_toml: Path, tmp_path: Path) -> None:
    """Given the bundled check.toml.sample loaded into a GatecheckConfig, When
    dumped then reloaded, Then the reloaded config equals the original."""
    # Arrange
    from gatecheck.config import dump_config

    cfg1 = load_config(sample_check_toml)
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg1, out)
    cfg2 = load_config(out)

    # Assert
    assert cfg1 == cfg2


# ---------------------------------------------------------------------------
# Field serialisation — ``from`` alias
# ---------------------------------------------------------------------------


def test_hook_from_field_uses_toml_alias(tmp_path: Path) -> None:
    """Given a HookDef whose ``from_`` is set, When dumped, Then the output TOML
    contains ``from =`` and does NOT contain ``from_ =``."""
    # Arrange
    from gatecheck.config import dump_config

    hook = HookDef(id="mypy", **{"from": "project", "run": "mypy src"})
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "from =" in text
    assert "from_ =" not in text
    assert "from_=" not in text


# ---------------------------------------------------------------------------
# None-field suppression
# ---------------------------------------------------------------------------


def test_none_field_absent_from_output(tmp_path: Path) -> None:
    """Given a HookDef with ``files=None`` (the default), When dumped, Then the
    key ``files`` does NOT appear in the output."""
    # Arrange
    from gatecheck.config import dump_config

    hook = _minimal_hook()
    assert hook.files is None
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "files" not in text


# ---------------------------------------------------------------------------
# Default-value suppression
# ---------------------------------------------------------------------------


def test_default_pass_files_absent(tmp_path: Path) -> None:
    """Given a HookDef with ``pass_files=True`` (the default), When dumped, Then
    ``pass-files`` does NOT appear in the output."""
    # Arrange
    from gatecheck.config import dump_config

    hook = HookDef(id="h", **{"from": "pypi:x", "run": "x", "pass-files": True})
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "pass-files" not in text


def test_non_default_pass_files_present(tmp_path: Path) -> None:
    """Given a HookDef with ``pass_files=False`` (non-default), When dumped, Then
    ``pass-files`` IS present in the output."""
    # Arrange
    from gatecheck.config import dump_config

    hook = HookDef(id="h", **{"from": "pypi:x", "run": "x", "pass-files": False})
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "pass-files" in text


def test_default_depends_on_absent(tmp_path: Path) -> None:
    """Given a HookDef with ``depends_on=[]`` (the default), When dumped, Then
    ``depends-on`` does NOT appear in the output."""
    # Arrange
    from gatecheck.config import dump_config

    hook = _minimal_hook()
    assert hook.depends_on == []
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "depends-on" not in text


def test_non_default_depends_on_present(tmp_path: Path) -> None:
    """Given a HookDef with ``depends_on=["ruff"]`` (non-default), When dumped,
    Then ``depends-on`` IS present in the output."""
    # Arrange
    from gatecheck.config import dump_config

    hook = HookDef(id="h", **{"from": "pypi:x", "run": "x", "depends-on": ["ruff"]})
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "depends-on" in text


# ---------------------------------------------------------------------------
# Inline-table ``when``
# ---------------------------------------------------------------------------


def test_when_is_inline_table(tmp_path: Path) -> None:
    """Given a HookDef with ``when=HookWhen(env_not="SKIP")``, When dumped, Then
    the output contains ``when = {`` (inline-table syntax) and does NOT expand
    ``when`` into a sub-table header like ``[hook.0.when]``."""
    # Arrange
    from gatecheck.config import dump_config

    hook = HookDef(
        id="h",
        **{"from": "pypi:x", "run": "x", "when": HookWhen(**{"env-not": "SKIP"})},
    )
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "when = {" in text or "when={" in text
    # Must not have expanded into a dotted sub-table header.
    assert ".when]" not in text


def test_richer_when_and_exclude_round_trip(tmp_path: Path) -> None:
    """The GAT-30 fields (branch* / files-match / env, plus hook-level exclude)
    survive a dump → load round-trip via the generic model_dump path."""
    # Arrange
    from gatecheck.config import dump_config, load_config

    hook = HookDef(
        id="h",
        **{
            "from": "pypi:x",
            "run": "x",
            "exclude": "vendor/*",
            "when": HookWhen(
                **{
                    "env": "DEPLOY",
                    "branch-matches": "release/*",
                    "branch-not": "wip/*",
                    "files-match": "*.py",
                }
            ),
        },
    )
    cfg = GatecheckConfig(hook=[hook])
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    reloaded = load_config(out)

    # Assert — the reloaded config equals the original
    assert reloaded == cfg
    when = reloaded.hook[0].when
    assert when is not None
    assert when.env == "DEPLOY"
    assert when.branch_matches == "release/*"
    assert when.branch_not == "wip/*"
    assert when.files_match == "*.py"
    assert reloaded.hook[0].exclude == "vendor/*"


# ---------------------------------------------------------------------------
# AoT count
# ---------------------------------------------------------------------------


def test_aot_count_matches_hooks(tmp_path: Path) -> None:
    """Given a config with exactly 3 hooks, When dumped, Then the output contains
    exactly 3 ``[[hook]]`` headers."""
    # Arrange
    from gatecheck.config import dump_config

    hooks = [
        _minimal_hook("h1"),
        _minimal_hook("h2"),
        _minimal_hook("h3"),
    ]
    cfg = GatecheckConfig(hook=hooks)
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert text.count("[[hook]]") == 3


# ---------------------------------------------------------------------------
# Group table headers
# ---------------------------------------------------------------------------


def test_group_header_present(tmp_path: Path) -> None:
    """Given a config with a single group named ``lint``, When dumped, Then
    ``[group.lint]`` is present in the output."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig(
        hook=[_minimal_hook("ruff")],
        group={"lint": GroupDef(hooks=["ruff"])},
    )
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "[group.lint]" in text


def test_multiple_groups_headers_present(tmp_path: Path) -> None:
    """Given a config with two groups, When dumped, Then both group headers are
    present in the output."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig(
        hook=[_minimal_hook("ruff"), _minimal_hook("mypy", from_="project", run="mypy src")],
        group={
            "lint": GroupDef(hooks=["ruff"]),
            "typecheck": GroupDef(hooks=["mypy"]),
        },
    )
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "[group.lint]" in text
    assert "[group.typecheck]" in text


# ---------------------------------------------------------------------------
# Error path — directory
# ---------------------------------------------------------------------------


def test_path_is_directory_raises(tmp_path: Path) -> None:
    """Given that ``path`` is an existing directory, When dump_config runs, Then
    IsADirectoryError (or OSError) is raised."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig()

    # Act & Assert
    with pytest.raises((IsADirectoryError, OSError)):
        dump_config(cfg, tmp_path)


# ---------------------------------------------------------------------------
# [sources] table
# ---------------------------------------------------------------------------


def test_sources_section_present_when_set(tmp_path: Path) -> None:
    """Given a config with sources.default_registry set, When dumped, Then
    ``[sources]`` and ``default-registry`` are both present in the output."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig(sources=SourceSpec(**{"default-registry": "https://pypi.org/simple"}))
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "[sources]" in text
    assert "default-registry" in text


def test_sources_absent_when_none(tmp_path: Path) -> None:
    """Given a config with ``sources=None``, When dumped, Then ``[sources]`` does
    NOT appear in the output."""
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig(sources=None)
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "[sources]" not in text


def test_sources_absent_when_empty_source_spec(tmp_path: Path) -> None:
    """Given a config with ``sources=SourceSpec()`` (all fields None), When dumped,
    Then ``[sources]`` does NOT appear in the output.

    SourceSpec() is a valid in-memory state where model_dump produces sources: {}
    (non-None object but empty dict after exclude_none). The _build_document guard
    ``isinstance(sources_data, dict) and sources_data`` must reject the empty dict.
    """
    # Arrange
    from gatecheck.config import dump_config

    cfg = GatecheckConfig(sources=SourceSpec())
    out = tmp_path / "check.toml"

    # Act
    dump_config(cfg, out)
    text = out.read_text(encoding="utf-8")

    # Assert
    assert "[sources]" not in text
