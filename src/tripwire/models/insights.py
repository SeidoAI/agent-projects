"""Agent-proposed concept node insights.

Written by the execution agent at `sessions/<id>/insights.yaml` as it
wraps up work. The PM reviews proposals at session-complete time — each
becomes a new node, a node update, or a rejection recorded to
`insights.rejected.yaml` for audit.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeProposal(BaseModel):
    """One proposed node addition or update.

    ``type`` is required for ``new_node`` (it becomes the `ConceptNode.type`);
    ``update_node`` leaves it blank and preserves the existing node's type.
    The value is validated against the project's active ``node_type`` enum
    when insights are loaded by ``load_insights``.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["new_node", "update_node"]
    id: str
    type: str | None = None
    name: str | None = None
    body: str | None = None
    delta: str | None = None
    related: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def _validate_fields_per_kind(self) -> NodeProposal:
        if self.kind == "new_node":
            if not self.body:
                raise ValueError("new_node proposals require `body`")
            if not self.name:
                raise ValueError("new_node proposals require `name`")
            if not self.type:
                raise ValueError("new_node proposals require `type`")
        elif self.kind == "update_node":
            if not self.delta:
                raise ValueError("update_node proposals require `delta`")
        return self


class InsightsFile(BaseModel):
    """Contents of `sessions/<id>/insights.yaml`."""

    model_config = ConfigDict(extra="forbid")

    proposals: list[NodeProposal] = Field(default_factory=list)
