"""SourceResolutionError — raised when a source cannot be located (BUILD-0005-ARCH §5)."""

from __future__ import annotations


class SourceResolutionError(ValueError):
    """Raised by ``resolve_source`` when a source cannot be located.

    Mirrors ``SourceSpecError``'s shape — subclasses ``ValueError``, carries
    structured ``tool`` / ``kind`` / ``reason``, and is location-free. Unlike a
    ``SourceSpecError`` (a *syntax* error knowable at load time), this is a
    **runtime/environment** condition: the spec is valid but the tool is absent
    on this machine, so it does NOT map to ``ConfigError``.
    """

    tool: str
    kind: str
    reason: str

    def __init__(self, tool: str, kind: str, reason: str) -> None:
        self.tool = tool
        self.kind = kind
        self.reason = reason
        super().__init__(f"cannot resolve '{tool}' from {kind} source: {reason}")
