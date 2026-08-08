"""Unit tests for the locked pydantic schema models (STY-0001 / TSK-001).

These tests exercise the four pydantic models defined by BUILD-0001-ARCH §3:

* ``SourceSpec``      — ``[sources]`` table
* ``HookDef``         — ``[[hook]]`` table entry
* ``HookWhen``        — nested inline-table model (lives in ``hook_def.py``)
* ``GroupDef``        — ``[group.<name>]`` table
* ``HooksmithConfig`` — top-level document

They lock the schema contract that Lane D's implementation MUST satisfy. In
particular, every hyphenated TOML alias from BUILD-0001-ARCH §7 is exercised
alongside its Python attribute form, so the alias scheme cannot regress
without breaking a test.

These tests intentionally fail on import while the new module files in
``src/hooksmith/config/`` do not yet exist — that is the RED state that
Lane D will turn GREEN.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hooksmith.config.group_def import GroupDef
from hooksmith.config.hook_def import HookDef, HookWhen
from hooksmith.config.hooksmith_config import HooksmithConfig
from hooksmith.config.source_spec import SourceSpec

# ──────────────────────────────────────────────────────────────────────────
# SourceSpec
# ──────────────────────────────────────────────────────────────────────────


def test_source_spec_default_registry_optional() -> None:
    """Given no arguments, When SourceSpec() is built, Then default_registry is None."""
    # Arrange
    # (no inputs)

    # Act
    spec = SourceSpec()

    # Assert
    assert spec.default_registry is None


def test_source_spec_accepts_default_registry_value() -> None:
    """Given a Python attribute name, When SourceSpec is built, Then the value is stored."""
    # Arrange
    registry_url = "https://pypi.org/simple"

    # Act
    spec = SourceSpec(default_registry=registry_url)

    # Assert
    assert spec.default_registry == registry_url


def test_source_spec_accepts_alias_form() -> None:
    """Given the hyphenated TOML alias, When SourceSpec is built, Then it succeeds and the
    value populates the snake_case attribute."""
    # Arrange
    payload = {"default-registry": "https://pypi.org/simple"}

    # Act
    spec = SourceSpec(**payload)

    # Assert
    assert spec.default_registry == "https://pypi.org/simple"


def test_source_spec_rejects_unknown_key() -> None:
    """Given an unknown key, When SourceSpec is built, Then ValidationError is raised
    (extra='forbid')."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        SourceSpec(unknown_key="x")

    errors = exc_info.value.errors()
    assert any("unknown_key" in str(err.get("loc", ())) for err in errors)


def test_source_spec_rejects_empty_default_registry() -> None:
    """Given default_registry=='', When SourceSpec is built, Then ValidationError
    is raised (arch §3.1: 'must be non-empty string')."""
    # Arrange / Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        SourceSpec(default_registry="")

    errors = exc_info.value.errors()
    assert any("default_registry" in str(err.get("loc", ())) for err in errors)


# ──────────────────────────────────────────────────────────────────────────
# HookDef
# ──────────────────────────────────────────────────────────────────────────


def test_hook_def_minimal() -> None:
    """Given only the three required fields, When HookDef is built, Then optional
    fields take their documented defaults."""
    # Arrange
    # (inline kwargs below)

    # Act
    hook = HookDef(id="x", from_="pypi:x", run="x")

    # Assert
    assert hook.id == "x"
    assert hook.from_ == "pypi:x"
    assert hook.run == "x"
    assert hook.files is None
    assert hook.pass_files is True
    assert hook.depends_on == []
    assert hook.when is None


def test_hook_def_accepts_full_record_via_python_attrs() -> None:
    """Given every field set via Python attribute names, When HookDef is built, Then
    all fields are populated and the nested HookWhen is constructed."""
    # Arrange
    when_payload = {"env_not": "SKIP_MYPY", "on_ci": True}

    # Act
    hook = HookDef(
        id="mypy",
        from_="pypi:mypy",
        run="mypy .",
        files="**/*.py",
        pass_files=False,
        depends_on=["ruff"],
        when=when_payload,
    )

    # Assert
    assert hook.id == "mypy"
    assert hook.from_ == "pypi:mypy"
    assert hook.run == "mypy ."
    assert hook.files == "**/*.py"
    assert hook.pass_files is False
    assert hook.depends_on == ["ruff"]
    assert hook.when is not None
    assert hook.when.env_not == "SKIP_MYPY"
    assert hook.when.on_ci is True


def test_hook_def_accepts_full_record_via_aliases() -> None:
    """Given every field set via TOML alias names, When HookDef is built, Then all
    fields are populated correctly."""
    # Arrange
    payload = {
        "id": "mypy",
        "from": "pypi:mypy",
        "run": "mypy .",
        "files": "**/*.py",
        "pass-files": False,
        "depends-on": ["ruff"],
        "when": {"env-not": "SKIP_MYPY", "on-ci": True},
    }

    # Act
    hook = HookDef(**payload)

    # Assert
    assert hook.id == "mypy"
    assert hook.from_ == "pypi:mypy"
    assert hook.run == "mypy ."
    assert hook.files == "**/*.py"
    assert hook.pass_files is False
    assert hook.depends_on == ["ruff"]
    assert hook.when is not None
    assert hook.when.env_not == "SKIP_MYPY"
    assert hook.when.on_ci is True


def test_hook_def_uses_alias_for_from_keyword() -> None:
    """Given the reserved ``from`` keyword as a key, When HookDef is built, Then the
    alias resolves to the ``from_`` attribute."""
    # Arrange
    payload = {"id": "x", "from": "pypi:x", "run": "x"}

    # Act
    hook = HookDef(**payload)

    # Assert
    assert hook.from_ == "pypi:x"


def test_hook_def_uses_alias_for_hyphenated_pass_files() -> None:
    """Given the hyphenated ``pass-files`` alias, When HookDef is built, Then the value
    populates the ``pass_files`` snake_case attribute."""
    # Arrange
    payload = {"id": "x", "from": "pypi:x", "run": "x", "pass-files": False}

    # Act
    hook = HookDef(**payload)

    # Assert
    assert hook.pass_files is False


def test_hook_def_uses_alias_for_depends_on() -> None:
    """Given the hyphenated ``depends-on`` alias, When HookDef is built, Then the list
    populates the ``depends_on`` snake_case attribute."""
    # Arrange
    payload = {
        "id": "x",
        "from": "pypi:x",
        "run": "x",
        "depends-on": ["a", "b"],
    }

    # Act
    hook = HookDef(**payload)

    # Assert
    assert hook.depends_on == ["a", "b"]


def test_hook_def_requires_id() -> None:
    """Given ``id`` is missing, When HookDef is built, Then ValidationError mentions
    the ``id`` field."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HookDef(from_="pypi:x", run="x")

    errors = exc_info.value.errors()
    assert any("id" in str(err.get("loc", ())) for err in errors)


def test_hook_def_requires_from() -> None:
    """Given ``from`` is missing, When HookDef is built, Then ValidationError mentions
    the ``from`` field."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HookDef(id="x", run="x")

    errors = exc_info.value.errors()
    error_locs = [str(err.get("loc", ())) for err in errors]
    assert any("from" in loc for loc in error_locs)


def test_hook_def_requires_run() -> None:
    """Given ``run`` is missing, When HookDef is built, Then ValidationError is raised."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HookDef(id="x", from_="pypi:x")

    errors = exc_info.value.errors()
    assert any("run" in str(err.get("loc", ())) for err in errors)


def test_hook_def_rejects_extra_field() -> None:
    """Given an unknown field, When HookDef is built, Then ValidationError mentions the
    extra key (extra='forbid')."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HookDef(id="x", from_="pypi:x", run="x", foo="bar")

    errors = exc_info.value.errors()
    assert any("foo" in str(err.get("loc", ())) for err in errors)


def test_hook_def_when_nested_model() -> None:
    """Given a ``when`` dict using TOML aliases, When HookDef is built, Then the inline
    table is validated into a HookWhen instance."""
    # Arrange
    payload = {
        "id": "x",
        "from_": "pypi:x",
        "run": "x",
        "when": {"env-not": "SKIP_MYPY"},
    }

    # Act
    hook = HookDef(**payload)

    # Assert
    assert hook.when is not None
    assert hook.when.env_not == "SKIP_MYPY"
    assert hook.when.on_ci is None


def test_hook_def_when_rejects_unknown_nested_key() -> None:
    """Given an unknown key inside ``when``, When HookDef is built, Then ValidationError
    is raised (HookWhen also uses extra='forbid')."""
    # Arrange
    payload = {
        "id": "x",
        "from_": "pypi:x",
        "run": "x",
        "when": {"unknown-key": "x"},
    }

    # Act / Assert
    with pytest.raises(ValidationError):
        HookDef(**payload)


# ──────────────────────────────────────────────────────────────────────────
# HookWhen
# ──────────────────────────────────────────────────────────────────────────


def test_hook_when_both_keys_optional() -> None:
    """Given no arguments, When HookWhen() is built, Then both fields default to None."""
    # Arrange
    # (no inputs)

    # Act
    when = HookWhen()

    # Assert
    assert when.env_not is None
    assert when.on_ci is None


def test_hook_when_on_ci_tri_state_omitted() -> None:
    """Given on_ci is omitted, When HookWhen is built, Then it is None (tri-state)."""
    # Arrange
    # (no inputs)

    # Act
    when = HookWhen()

    # Assert
    assert when.on_ci is None


def test_hook_when_on_ci_tri_state_true() -> None:
    """Given on_ci=True, When HookWhen is built, Then the attribute is True."""
    # Arrange
    # (inline kwargs below)

    # Act
    when = HookWhen(on_ci=True)

    # Assert
    assert when.on_ci is True


def test_hook_when_on_ci_tri_state_false() -> None:
    """Given on_ci=False, When HookWhen is built, Then the attribute is False."""
    # Arrange
    # (inline kwargs below)

    # Act
    when = HookWhen(on_ci=False)

    # Assert
    assert when.on_ci is False


def test_hook_when_on_ci_alias_form() -> None:
    """Given the hyphenated ``on-ci`` alias, When HookWhen is built, Then the snake_case
    attribute is populated."""
    # Arrange
    payload = {"on-ci": True}

    # Act
    when = HookWhen(**payload)

    # Assert
    assert when.on_ci is True


def test_hook_when_env_not_alias() -> None:
    """Given the hyphenated ``env-not`` alias, When HookWhen is built, Then the snake_case
    attribute is populated."""
    # Arrange
    payload = {"env-not": "SKIP_X"}

    # Act
    when = HookWhen(**payload)

    # Assert
    assert when.env_not == "SKIP_X"


def test_hook_when_requires_network_alias() -> None:
    """Given the hyphenated ``requires-network`` alias, When HookWhen is built, Then the
    snake_case attribute is populated."""
    # Arrange
    payload = {"requires-network": True}

    # Act
    when = HookWhen(**payload)

    # Assert
    assert when.requires_network is True


# ──────────────────────────────────────────────────────────────────────────
# GroupDef
# ──────────────────────────────────────────────────────────────────────────


def test_group_def_minimal() -> None:
    """Given only ``hooks``, When GroupDef is built, Then all other fields take their
    documented defaults."""
    # Arrange
    # (inline kwargs below)

    # Act
    group = GroupDef(hooks=["a"])

    # Assert
    assert group.hooks == ["a"]
    assert group.parallel is False
    assert group.fail_fast is False
    assert group.max_workers == 4
    assert group.on_event is None


def test_group_def_max_workers_alias_and_value() -> None:
    """Given the hyphenated ``max-workers`` alias, When GroupDef is built, Then the
    snake_case attribute carries the value."""
    # Act
    group = GroupDef(**{"hooks": ["a"], "max-workers": 8})
    # Assert
    assert group.max_workers == 8


def test_group_def_rejects_zero_max_workers() -> None:
    """Given ``max-workers = 0``, When GroupDef is built, Then ValidationError is
    raised (a cap must be at least 1)."""
    # Act / Assert
    with pytest.raises(ValidationError):
        GroupDef(**{"hooks": ["a"], "max-workers": 0})


def test_group_def_requires_hooks() -> None:
    """Given no ``hooks`` field, When GroupDef() is built, Then ValidationError mentions
    the ``hooks`` field."""
    # Arrange
    # (no inputs)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        GroupDef()

    errors = exc_info.value.errors()
    assert any("hooks" in str(err.get("loc", ())) for err in errors)


def test_group_def_rejects_empty_hooks() -> None:
    """Given ``hooks=[]``, When GroupDef is built, Then ValidationError is raised
    (BUILD-0001-ARCH §3.3: must be non-empty list)."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError):
        GroupDef(hooks=[])


def test_group_def_rejects_empty_string_in_hooks() -> None:
    """Given ``hooks=[""]``, When GroupDef is built, Then ValidationError is raised
    (BUILD-0001-ARCH §3.3: each entry must be a non-empty string)."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError):
        GroupDef(hooks=[""])


def test_group_def_uses_alias_fail_fast() -> None:
    """Given the hyphenated ``fail-fast`` alias, When GroupDef is built, Then the
    snake_case attribute is populated."""
    # Arrange
    payload = {"hooks": ["a"], "fail-fast": True}

    # Act
    group = GroupDef(**payload)

    # Assert
    assert group.fail_fast is True


@pytest.mark.parametrize("event", ["commit", "push", "commit-msg"])
def test_group_def_on_event_accepts_each_supported_event(event: str) -> None:
    """Given each supported ``on-event`` value, When GroupDef is built, Then it's kept."""
    # Act
    group = GroupDef(**{"hooks": ["a"], "on-event": event})
    # Assert
    assert group.on_event == event


def test_group_def_on_event_literal_rejects_unknown_value() -> None:
    """Given an ``on_event`` value not in the locked Literal set, When GroupDef is built,
    Then ValidationError is raised."""
    # Act / Assert — 'merge' is not a supported git event for hooksmith
    with pytest.raises(ValidationError):
        GroupDef(hooks=["a"], on_event="merge")


def test_group_def_rejects_extra_field() -> None:
    """Given an unknown field, When GroupDef is built, Then ValidationError mentions the
    extra key (extra='forbid')."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        GroupDef(hooks=["a"], unknown="x")

    errors = exc_info.value.errors()
    assert any("unknown" in str(err.get("loc", ())) for err in errors)


# ──────────────────────────────────────────────────────────────────────────
# HooksmithConfig
# ──────────────────────────────────────────────────────────────────────────


def test_hooksmith_config_empty() -> None:
    """Given no inputs, When HooksmithConfig() is built, Then all top-level fields take
    their documented defaults."""
    # Arrange
    # (no inputs)

    # Act
    cfg = HooksmithConfig()

    # Assert
    assert cfg.hook == []
    assert cfg.group == {}
    assert cfg.sources is None


def test_hooksmith_config_full() -> None:
    """Given a hook, a group, and a sources table, When HooksmithConfig is built, Then
    every nested model is validated and accessible."""
    # Arrange
    payload = {
        "hook": [
            {
                "id": "ruff",
                "from": "pypi:ruff",
                "run": "ruff check .",
                "pass-files": False,
            }
        ],
        "group": {"pre-commit": {"hooks": ["ruff"], "fail-fast": True, "on-event": "commit"}},
        "sources": {"default-registry": "https://pypi.org/simple"},
    }

    # Act
    cfg = HooksmithConfig(**payload)

    # Assert
    assert len(cfg.hook) == 1
    assert cfg.hook[0].id == "ruff"
    assert cfg.hook[0].from_ == "pypi:ruff"
    assert cfg.hook[0].pass_files is False
    assert "pre-commit" in cfg.group
    assert cfg.group["pre-commit"].hooks == ["ruff"]
    assert cfg.group["pre-commit"].fail_fast is True
    assert cfg.group["pre-commit"].on_event == "commit"
    assert cfg.sources is not None
    assert cfg.sources.default_registry == "https://pypi.org/simple"


def test_hooksmith_config_rejects_extra_field() -> None:
    """Given an unknown top-level key, When HooksmithConfig is built, Then ValidationError
    is raised (extra='forbid')."""
    # Arrange
    # (inline kwargs below)

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HooksmithConfig(unknown="x")

    errors = exc_info.value.errors()
    assert any("unknown" in str(err.get("loc", ())) for err in errors)


def test_hooksmith_config_validates_nested_hook() -> None:
    """Given an incomplete hook (missing ``from`` and ``run``), When HooksmithConfig is
    built, Then ValidationError surfaces the nested error path mentioning ``hook[0]``."""
    # Arrange
    payload = {"hook": [{"id": "a"}]}

    # Act / Assert
    with pytest.raises(ValidationError) as exc_info:
        HooksmithConfig(**payload)

    errors = exc_info.value.errors()
    error_locs = [str(err.get("loc", ())) for err in errors]
    assert any("hook" in loc and "0" in loc for loc in error_locs)
