"""Concept node model.

A concept node is a named, versioned pointer to a concrete artifact in the
codebase. Issues reference nodes by `[[node-id]]` so that when code moves,
one node file is updated instead of N issues.
"""

import re
import uuid as _uuid
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

NODE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")

NodeOrigin = Literal["workspace", "local"]
NodeScope = Literal["workspace", "local"]


class NodeSource(BaseModel):
    """Where the concept lives in the codebase.

    Optional: a `planned` node has no source yet; a `decision` node may
    point to a doc rather than code.
    """

    model_config = ConfigDict(extra="forbid")

    repo: str
    path: str
    # Inclusive 1-indexed line range. Optional — omit for whole-file references.
    lines: tuple[int, int] | None = None
    branch: str | None = None
    # SHA-256 hash of the content at this location, e.g. "sha256:abc...".
    content_hash: str | None = None


class ConceptNode(BaseModel):
    """A node in the concept graph.

    Mirrors the YAML frontmatter + optional Markdown body file format under
    `nodes/<id>.yaml`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Canonical identity (never changes)
    uuid: UUID = Field(default_factory=_uuid.uuid4)

    # Human-readable slug, unique within a project (filename = id).
    id: str

    type: str
    name: str
    description: str | None = None

    source: NodeSource | None = None

    related: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    status: str = "active"

    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    body: str = ""

    # v0.6b workspace integration fields.
    # Existing nodes load with the defaults (local/local, no workspace_sha).
    origin: NodeOrigin = "local"
    scope: NodeScope = "local"
    workspace_sha: str | None = None
    workspace_pulled_at: datetime | None = None

    @field_validator("id")
    @classmethod
    def _validate_id_format(cls, v: str) -> str:
        if not NODE_ID_PATTERN.match(v):
            raise ValueError(
                f"Node id {v!r} must be a lowercase slug "
                f"(letters, digits, hyphens). Pattern: {NODE_ID_PATTERN.pattern}"
            )
        return v

    @model_validator(mode="after")
    def _workspace_sha_consistent_with_origin(self) -> "ConceptNode":
        """workspace_sha is project-side bookkeeping — only meaningful when
        origin=workspace. Canonical workspace nodes (in the workspace repo)
        don't carry it, and local-origin project nodes must not carry it.
        """
        if self.origin == "local" and self.workspace_sha is not None:
            raise ValueError("workspace_sha is forbidden when origin=local")
        return self
