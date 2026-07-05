"""Unit tests for gatecheck.registry.index_resolver.resolve_index_url (STY-0006).

Contract under test is LOCKED by
``planning/build-plans/0006-architecture-decision.md`` §2 / §4 step 1:

``resolve_index_url(registry, sources)`` is a PURE alias -> index-URL function
with NO network and no ``packaging`` dependency:

- ``registry is None`` -> ``sources.default_registry`` if set, else the built-in
  default ``https://pypi.org/simple`` (also used when ``sources`` is ``None``).
- ``registry == "<alias>"`` -> ``sources.extra_registries["<alias>"]``.
- an undeclared alias (or ``sources is None``) -> ``RegistryError`` with
  ``index_url is None`` whose reason names the alias and
  ``[sources].extra-registries``.

``resolve_index_url`` lives in the ``index_resolver`` submodule (§2); it is not part
of the facade ``__all__``, so it is imported here from the submodule directly. AAA
throughout. No mocks, no network — clean (slash-free) URLs are used so the
assertions hold regardless of trailing-slash normalization.
"""

from __future__ import annotations

import pytest

from gatecheck.config import SourceSpec
from gatecheck.registry import RegistryError
from gatecheck.registry.index_resolver import resolve_index_url

BUILTIN_DEFAULT = "https://pypi.org/simple"


# ---------------------------------------------------------------------------
# registry is None -> default_registry, else built-in default
# ---------------------------------------------------------------------------


def test_none_registry_uses_default_registry_when_set() -> None:
    # Arrange
    sources = SourceSpec(default_registry="https://custom.example.com/simple")

    # Act
    result = resolve_index_url(None, sources)

    # Assert
    assert result == "https://custom.example.com/simple"


def test_none_registry_falls_back_to_builtin_when_no_default() -> None:
    # Arrange — SourceSpec present but default_registry unset.
    sources = SourceSpec()

    # Act
    result = resolve_index_url(None, sources)

    # Assert
    assert result == BUILTIN_DEFAULT


def test_none_registry_and_none_sources_uses_builtin() -> None:
    # Arrange / Act
    result = resolve_index_url(None, None)

    # Assert
    assert result == BUILTIN_DEFAULT


# ---------------------------------------------------------------------------
# declared alias -> its URL
# ---------------------------------------------------------------------------


def test_declared_alias_resolves_to_its_url() -> None:
    # Arrange
    sources = SourceSpec(**{"extra-registries": {"internal": "https://pkg.example.com/simple"}})

    # Act
    result = resolve_index_url("internal", sources)

    # Assert
    assert result == "https://pkg.example.com/simple"


# ---------------------------------------------------------------------------
# undeclared alias -> RegistryError (index_url None)
# ---------------------------------------------------------------------------


def test_undeclared_alias_raises_registry_error() -> None:
    # Arrange — "other" is not among the declared registries.
    sources = SourceSpec(**{"extra-registries": {"internal": "https://pkg.example.com/simple"}})

    # Act
    with pytest.raises(RegistryError) as exc_info:
        resolve_index_url("other", sources)

    # Assert
    err = exc_info.value
    assert err.index_url is None
    assert "other" in err.reason
    assert "[sources].extra-registries" in err.reason


def test_alias_with_none_sources_raises_registry_error() -> None:
    # Arrange / Act — no [sources] table at all.
    with pytest.raises(RegistryError) as exc_info:
        resolve_index_url("internal", None)

    # Assert
    err = exc_info.value
    assert err.index_url is None
    assert "internal" in err.reason
