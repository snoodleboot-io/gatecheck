"""HookDef + HookWhen models — `[[hook]]` table entry (BUILD-0001-ARCH §3.2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, StrictBool


class HookWhen(BaseModel):
    """Pydantic model for the inline-table `when = { ... }` on a hook.

    All present conditions are AND-ed: the hook runs only when every one passes.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    env: str | None = Field(default=None)
    env_not: str | None = Field(default=None, alias="env-not")
    on_ci: StrictBool | None = Field(default=None, alias="on-ci")
    branch: str | None = Field(default=None)
    branch_not: str | None = Field(default=None, alias="branch-not")
    branch_matches: str | None = Field(default=None, alias="branch-matches")
    files_match: str | None = Field(default=None, alias="files-match")
    requires_network: StrictBool | None = Field(default=None, alias="requires-network")


class HookDef(BaseModel):
    """Pydantic model for a single `[[hook]]` table entry in check.toml."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str = Field(min_length=1)
    from_: str = Field(alias="from", min_length=1)
    run: str = Field(min_length=1)
    files: str | None = Field(default=None)
    exclude: str | None = Field(default=None)
    pass_files: StrictBool = Field(default=True, alias="pass-files")
    depends_on: list[str] = Field(default_factory=list, alias="depends-on")
    when: HookWhen | None = Field(default=None)
