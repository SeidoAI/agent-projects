"""SessionHandoff model — structured handoff record at session launch.

Lives at sessions/<id>/handoff.yaml. The PM agent writes it when
launching a session; the execution agent reads it first thing on start.
Provides the PM-to-execution-agent channel that was previously a
free-form markdown comment.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tripwire.core.branch_naming import is_valid_branch_name

HandedOffBy = Literal["pm", "execution-agent", "verification-agent"]


class WorkspaceContext(BaseModel):
    """Optional workspace-aware handoff fields (populated when project
    has a workspace pointer)."""

    model_config = ConfigDict(extra="forbid")

    workspace_nodes_touched: list[str] = Field(default_factory=list)
    workspace_sha_at_handoff: str | None = None
    stale_nodes: list[str] = Field(default_factory=list)


class SessionHandoff(BaseModel):
    """Handoff record written at /pm-session-queue."""

    model_config = ConfigDict(extra="forbid")

    uuid: UUID
    session_id: str
    handoff_at: datetime
    handed_off_by: HandedOffBy
    branch: str
    open_questions: list[str] = Field(default_factory=list)
    context_to_preserve: list[str] = Field(default_factory=list)
    last_verification_passed_at: datetime | None = None
    workspace_context: WorkspaceContext | None = None

    @field_validator("branch")
    @classmethod
    def _validate_branch(cls, v: str) -> str:
        if not is_valid_branch_name(v):
            raise ValueError(f"branch '{v}' does not match <type>/<slug> convention")
        return v
