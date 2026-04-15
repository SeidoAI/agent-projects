"""Workspace model (v0.6b).

A workspace is a centralized shared-concepts layer for N projects.
workspace.yaml lives at the workspace repo root and maintains the
bidirectional registry of projects with their last-sync state.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

SUPPORTED_SCHEMA_VERSIONS: tuple[int, ...] = (1,)


class WorkspaceProjectEntry(BaseModel):
    """One member project in a workspace's registry."""

    model_config = ConfigDict(extra="forbid")

    slug: str  # workspace-local alias, e.g. "kbp"
    name: str  # matches project.yaml.name
    path: str  # relative (to workspace root) or absolute

    last_pulled_sha: str | None = None
    last_pulled_at: datetime | None = None
    last_pushed_sha: str | None = None
    last_pushed_at: datetime | None = None


class Workspace(BaseModel):
    """workspace.yaml root."""

    model_config = ConfigDict(extra="forbid")

    uuid: UUID
    name: str
    slug: str
    description: str = ""
    schema_version: int = 1
    keel_version: str = "0.6.0"
    created_at: datetime
    updated_at: datetime
    projects: list[WorkspaceProjectEntry] = Field(default_factory=list)

    @model_validator(mode="after")
    def _schema_version_supported(self) -> "Workspace":
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ValueError(
                f"workspace schema_version {self.schema_version} not supported "
                f"(this keel supports {SUPPORTED_SCHEMA_VERSIONS})"
            )
        return self

    @model_validator(mode="after")
    def _project_slugs_unique(self) -> "Workspace":
        slugs = [p.slug for p in self.projects]
        if len(slugs) != len(set(slugs)):
            dups = {s for s in slugs if slugs.count(s) > 1}
            raise ValueError(f"duplicate project slugs in workspace: {dups}")
        return self
