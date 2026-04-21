"""Per-issue artifact manifest models.

Describes artifacts attached to an issue (developer.md, verified.md).
`produced_by`, `owned_by`, and `required_at_status` carry plain strings
on the model; validation against the active `agent_type` and
`issue_status` enums happens at manifest-load time in
`tripwire.core.issue_artifact_store.load_issue_artifact_manifest`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IssueArtifactEntry(BaseModel):
    """One entry in the per-issue artifact manifest."""

    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str
    produced_by: str
    owned_by: str | None = None
    required: bool = True
    required_at_status: str

    @model_validator(mode="after")
    def _default_owned_by_to_produced_by(self) -> IssueArtifactEntry:
        if self.owned_by is None:
            object.__setattr__(self, "owned_by", self.produced_by)
        return self


class IssueArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifacts: list[IssueArtifactEntry] = Field(default_factory=list)
