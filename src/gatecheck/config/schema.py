"""Pydantic models for the check.toml schema.

The shape mirrors `docs/config/reference.md`. STY-0001 fills in the field
definitions; this module is the contract every other subsystem reads.
"""

from __future__ import annotations

from pydantic import BaseModel


class SourceSpec(BaseModel):
    """A `from = "..."` source specification (pypi, project, system, ...)."""


class HookDef(BaseModel):
    """A `[[hook]]` table entry."""


class GroupDef(BaseModel):
    """A `[group.<name>]` table entry."""


class GatecheckConfig(BaseModel):
    """Top-level config object — the validated form of a check.toml file."""
