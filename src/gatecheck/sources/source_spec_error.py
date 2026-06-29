"""SourceSpecError — raised for a syntactically invalid `from` spec (BUILD-0004-ARCH §5)."""

from __future__ import annotations


class SourceSpecError(ValueError):
    """Raised by ``parse_source`` for a syntactically invalid ``from`` spec.

    Subclasses ``ValueError`` to stay consistent with ``ConfigError``. Carries
    structured ``spec`` + ``reason`` so the config layer can re-format the
    diagnostic without string-scraping. Location-free and I/O-free.
    """

    spec: str
    reason: str

    def __init__(self, spec: str, reason: str) -> None:
        self.spec = spec
        self.reason = reason
        super().__init__(f"invalid source spec '{spec}': {reason}")
