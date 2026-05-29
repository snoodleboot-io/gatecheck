"""ConfigError — wraps loader failures with IDE-style file/line/col context (BUILD-0002-ARCH §2)."""

from __future__ import annotations

from pathlib import Path


class ConfigError(ValueError):
    """Loader failure carrying ``path`` + one or more ``(line, col, msg)`` entries."""

    path: Path
    errors: list[tuple[int, int, str]]

    def __init__(self, path: Path, errors: list[tuple[int, int, str]]) -> None:
        if not errors:
            raise ValueError("ConfigError requires at least one error entry")
        self.path = path
        self.errors = errors
        super().__init__(self._render(path, errors))

    @staticmethod
    def _render(path: Path, errors: list[tuple[int, int, str]]) -> str:
        return "\n".join(f"{path}:{line}:{col}: {msg}" for line, col, msg in errors)

    def __str__(self) -> str:
        return self._render(self.path, self.errors)
