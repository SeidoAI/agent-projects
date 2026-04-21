"""ArtifactManifest model.

Manifests declare what every session must produce — per artifact: where
the file lives, which phase it's written in, who produces it, who owns
it.

`produced_at` / `produced_by` / `owned_by` are plain strings on the model.
They are validated at manifest-load time against the active
`artifact_phase.yaml` and `agent_type.yaml` enums (project override or
packaged default). See `tripwire.core.manifest_loader.load_artifact_manifest`.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArtifactEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    file: str
    template: str
    produced_at: str
    produced_by: str = "pm"
    owned_by: str | None = None
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
