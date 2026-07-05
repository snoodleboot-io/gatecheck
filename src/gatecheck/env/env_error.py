"""EnvError — raised when a hook cannot be resolved to an environment (BUILD-0007-ARCH §4)."""

from __future__ import annotations


class EnvError(ValueError):
    """Raised by ``EnvManager.resolve`` when a hook cannot be resolved to an environment.

    Mirrors ``SourceResolutionError`` / ``RegistryError`` — subclasses ``ValueError``,
    carries structured ``hook_id`` / ``reason`` fields, and is location-free. An
    env-resolution failure is a runtime/environment-domain condition (unresolvable
    tool name, a source kind not handled in this slice), NOT a ``check.toml`` syntax
    error, so it does NOT map to ``ConfigError`` and carries no ``line:col``.
    """

    hook_id: str
    reason: str

    def __init__(self, hook_id: str, reason: str) -> None:
        self.hook_id = hook_id
        self.reason = reason
        super().__init__(f"cannot resolve environment for hook '{hook_id}': {reason}")
