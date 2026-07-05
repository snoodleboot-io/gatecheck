"""resolve_index_url — alias → index-URL resolution against a SourceSpec (BUILD-0006-ARCH §4).

Pure: no network, no ``packaging`` dependency. Separated from ``pypi_resolver`` so
the alias→URL rules and the unknown-alias error path unit-test without a fake client.
"""

from __future__ import annotations

from gatecheck.config import SourceSpec
from gatecheck.registry.registry_error import RegistryError

DEFAULT_INDEX_URL = "https://pypi.org/simple"


def resolve_index_url(registry: str | None, sources: SourceSpec | None) -> str:
    """Resolve a registry alias (or ``None``) to a normalized index URL.

    ``registry is None`` → ``sources.default_registry`` if set, else the built-in
    ``https://pypi.org/simple``. ``registry == "<alias>"`` →
    ``sources.extra_registries["<alias>"]``, else ``RegistryError`` (unknown alias,
    ``index_url=None``). The returned URL has one trailing ``/`` stripped so
    ``{index_url}/{name}/`` is well-formed.
    """
    if registry is None:
        if sources is not None and sources.default_registry is not None:
            return _normalize(sources.default_registry)
        return DEFAULT_INDEX_URL

    extra = sources.extra_registries if sources is not None else {}
    if registry not in extra:
        raise RegistryError(
            requirement=registry,
            index_url=None,
            reason=(
                f"unknown registry alias '{registry}' (not declared in [sources].extra-registries)"
            ),
        )
    return _normalize(extra[registry])


def _normalize(url: str) -> str:
    """Strip a single trailing slash so ``{index_url}/{name}/`` is well-formed."""
    return url[:-1] if url.endswith("/") else url
