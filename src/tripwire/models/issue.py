"""Issue model.

An issue carries both a `uuid` (canonical identity, never changes) and an
`id` (human-readable sequential key like `SEI-42`, may be renamed during
collision resolution). Per KUI-158 the `status` field is typed as the
upstream `IssueStatus` enum so Pydantic enforces the contract at
model_validate time; project-side `enums/issue_status.yaml` is for UI
labels/colours, not for adding new statuses.
"""

import re
import uuid as _uuid
from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field, field_validator

from tripwire.models.enums import IssueStatus

ISSUE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


class Issue(BaseModel):
    """A single issue in a project.

    Mirrors the YAML frontmatter + Markdown body file format. The `body`
    field holds the Markdown body content; the rest are frontmatter fields.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Canonical identity (never changes)
    uuid: UUID4 = Field(default_factory=_uuid.uuid4)

    # Human-readable sequential key (e.g. SEI-42). May be renamed during
    # collision resolution; the `uuid` is the stable handle.
    id: str

    # Integer schema/contract version. KUI-126 / A1: bumped manually
    # when a contract change makes consumers' pinned references stale.
    # Bare `[[id]]` resolves to the latest; `[[id@vN]]` pins to N.
    version: int = 1

    # KUI-127 / A2: PM-set marker for the latest contract-change version.
    contract_changed_at: int | None = None

    title: str
    status: IssueStatus = IssueStatus.BACKLOG
    priority: str
    executor: str
    verifier: str

    # Conventional-commits-style kind. Optional; used by
    # `tripwire session derive-branch` to emit the canonical <type>/<slug>
    # branch name. Valid values track tripwire.core.branch_naming.ALLOWED_TYPES.
    kind: str | None = None

    agent: str | None = None
    labels: list[str] = Field(default_factory=list)
    parent: str | None = None
    repo: str | None = None
    base_branch: str | None = None

    implements: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    # `blocks` is computed by the graph cache from inverse `blocked_by`.
    # We accept it on read for round-trip fidelity but the validator will
    # rebuild it from the cache as the source of truth.
    blocks: list[str] = Field(default_factory=list)

    # Optional doc paths from the project repo, mounted read-only into the
    # container alongside agent-level and session-level docs.
    docs: list[str] | None = None

    created_at: datetime | None = None
    updated_at: datetime | None = None
    created_by: str | None = None

    # The Markdown body, parsed separately from frontmatter.
    body: str = ""

    @field_validator("id")
    @classmethod
    def _validate_id_format(cls, v: str) -> str:
        if not ISSUE_ID_PATTERN.match(v):
            raise ValueError(
                f"Issue id {v!r} must match <PREFIX>-<N> "
                f"(e.g. SEI-42). Pattern: {ISSUE_ID_PATTERN.pattern}"
            )
        return v
