"""Typed model of a .pre-commit-config.yaml (STY-0019 / GAT-19).

Only the fields the migration cares about are modeled; ``extra="ignore"`` lets the
many other pre-commit keys pass through harmlessly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PreCommitHook(BaseModel):
    """One ``hooks[]`` entry within a pre-commit repo."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1)
    name: str | None = None
    entry: str | None = None
    language: str | None = None
    files: str | None = None
    args: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    additional_dependencies: list[str] = Field(default_factory=list)


class PreCommitRepo(BaseModel):
    """One ``repos[]`` entry: a source repo and its hooks."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    repo: str = Field(min_length=1)
    rev: str | None = None
    hooks: list[PreCommitHook] = Field(default_factory=list)


class PreCommitConfig(BaseModel):
    """A parsed ``.pre-commit-config.yaml`` document."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    repos: list[PreCommitRepo] = Field(default_factory=list)
