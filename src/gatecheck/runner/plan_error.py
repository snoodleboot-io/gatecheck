"""PlanError — raised when an execution plan cannot be built (STY-0012 / GAT-14)."""

from __future__ import annotations


class PlanError(ValueError):
    """Raised by ``build_plan`` for an unbuildable plan.

    Covers an unknown group, a group referencing an unknown hook, a ``depends_on``
    referencing an unknown hook, and a dependency cycle. Subclasses ``ValueError``
    (mirroring ``EnvError`` / ``RegistryError`` / ``SourceResolutionError``); it is a
    runtime/config-domain condition, not a ``check.toml`` syntax error, so it carries
    no ``line:col`` and does not map to ``ConfigError``.
    """
