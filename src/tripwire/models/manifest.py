"""ArtifactManifest model.

Manifests declare what every session must produce — per artifact: where
the file lives, which phase it's written in, who produces it, who owns
it. v0.6a adds the ownership fields so the validator can enforce
stage-aware requirements.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AgentType = Literal["pm", "execution-agent", "verification-agent"]
ArtifactPhase = Literal["planning", "implementing", "verifying", "completion"]


class ArtifactEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str
    produced_at: ArtifactPhase
    produced_by: AgentType = "pm"
    owned_by: AgentType | None = None
    required: bool = True
    approval_gate: bool = False

    @model_validator(mode="after")
    def _default_owned_by_to_produced_by(self) -> ArtifactEntry:
        if self.owned_by is None:
            object.__setattr__(self, "owned_by", self.produced_by)
        return self


class ArtifactManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifacts: list[ArtifactEntry] = Field(default_factory=list)
