"""RegistryError — raised when a pypi source cannot be pinned (BUILD-0006-ARCH §6)."""

from __future__ import annotations


class RegistryError(ValueError):
    """Raised by ``resolve_pypi_source`` when a pypi source cannot be pinned.

    Mirrors ``SourceResolutionError``'s shape — subclasses ``ValueError``, carries
    structured ``requirement`` / ``index_url`` / ``reason``, and is location-free. A
    registry failure is a runtime/environment condition (network / index state), NOT
    a check.toml syntax error, so it does NOT map to ``ConfigError``. ``index_url`` is
    ``None`` only for the unknown-alias case (no URL resolved yet).
    """

    requirement: str
    index_url: str | None
    reason: str

    def __init__(self, requirement: str, index_url: str | None, reason: str) -> None:
        self.requirement = requirement
        self.index_url = index_url
        self.reason = reason
        loc = index_url if index_url is not None else "<unresolved index>"
        super().__init__(f"cannot resolve '{requirement}' against {loc}: {reason}")
