"""MigrationError — raised when a pre-commit config cannot be migrated (STY-0019 / GAT-19)."""

from __future__ import annotations


class MigrationError(ValueError):
    """Raised for a malformed or unmigratable ``.pre-commit-config.yaml``.

    Covers unreadable / invalid YAML, a wrong top-level shape, and schema
    validation failures. Subclasses ``ValueError`` (mirroring the other typed
    domain errors); it is a runtime condition, not a ``check.toml`` syntax error.
    """
