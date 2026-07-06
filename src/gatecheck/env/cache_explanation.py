"""CacheExplanation — a read-only explanation of a hook's cache state (STY-0009 / GAT-11).

Output value object of ``EnvManager.explain``: the resolved source, the derived
``cache_key`` and the exact material it was hashed from (so the digest reproduces by
hand), the cache directory, and the hit / miss / not-applicable status. Rendered by
``gatecheck cache why`` (human ``render()`` or ``--json`` via ``to_dict()``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CacheExplanation:
    """Why a hook does or does not have a cached environment."""

    hook_id: str
    source_kind: str  # "system" | "project" | "pypi"
    source_summary: str
    cache_key: str
    key_material: tuple[str, ...]
    cache_dir: str
    status: str  # "hit" | "miss" | "not-applicable"
    reason: str

    def to_dict(self) -> dict[str, object]:
        """Serialize to a plain dict for ``--json`` output."""
        return {
            "hook_id": self.hook_id,
            "source_kind": self.source_kind,
            "source_summary": self.source_summary,
            "cache_key": self.cache_key,
            "key_material": list(self.key_material),
            "cache_dir": self.cache_dir,
            "status": self.status,
            "reason": self.reason,
        }

    def render(self) -> str:
        """Render a human-readable report for ``gatecheck cache why``."""
        material = " + ".join(repr(part) for part in self.key_material)
        return "\n".join(
            [
                f"hook:      {self.hook_id}",
                f"source:    {self.source_summary}  ({self.source_kind})",
                f"status:    {self.status} — {self.reason}",
                f"cache key: {self.cache_key}",
                f"  hashed:  sha256({material})",
                f"cache dir: {self.cache_dir}",
            ]
        )
