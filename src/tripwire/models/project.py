"""ProjectConfig model — represents `<project>/project.yaml`.

The project config is the entry point for every CLI command and the
authoritative source for repo registry, status flow, label categories,
graph settings, the orchestration default, and the next-issue counter
used by `tripwire next-key`.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectPhase(str, Enum):
    """Workflow phases for phase-aware validation.

    The validator enforces different requirements depending on the current
    phase.  The PM agent advances the phase by editing ``project.yaml``
    directly; the validator blocks transitions that don't meet the
    phase-specific requirements.
    """

    scoping = "scoping"
    scoped = "scoped"
    executing = "executing"
    reviewing = "reviewing"


class RepoEntry(BaseModel):
    """One repo in `project.yaml.repos`.

    The repo is keyed in the parent dict by GitHub slug; the entry holds the
    optional local clone path used for fast freshness checks.
    """

    model_config = ConfigDict(extra="forbid")

    local: str | None = None


class GraphSettings(BaseModel):
    """`project.yaml.graph` — concept graph settings."""

    model_config = ConfigDict(extra="forbid")

    node_types: list[str] = Field(default_factory=list)
    auto_index: bool = True


class LabelCategories(BaseModel):
    """`project.yaml.label_categories` — categorised labels.

    Each category is a list of allowed values; an empty list means "any
    label in this category is allowed".
    """

    model_config = ConfigDict(extra="forbid")

    executor: list[str] = Field(default_factory=list)
    verifier: list[str] = Field(default_factory=list)
    domain: list[str] = Field(default_factory=list)
    agent: list[str] = Field(default_factory=list)


class OrchestrationConfig(BaseModel):
    """`project.yaml.orchestration` — orchestration defaults for the project.

    The named pattern is loaded from `<project>/orchestration/<name>.yaml`.
    Sessions can override either the named pattern or individual fields.
    """

    model_config = ConfigDict(extra="allow")

    default_pattern: str = "default"
    plan_approval_required: bool = False
    auto_merge_on_pass: bool = False


class ProjectWorkspacePointer(BaseModel):
    """Workspace this project is linked to (v0.6b).

    Object form reserves room for future extensions (remote URLs, pinning
    a workspace SHA). Currently only ``path`` is supported; URL support
    arrives in a later release.
    """

    model_config = ConfigDict(extra="forbid")

    path: str | None = None
    # url: str | None = None  # future

    @model_validator(mode="after")
    def _at_least_one_target(self) -> "ProjectWorkspacePointer":
        if self.path is None:  # and self.url is None
            raise ValueError("workspace pointer requires `path`")
        return self


class ProjectConfig(BaseModel):
    """The project's root config, parsed from `<project>/project.yaml`."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str
    key_prefix: str
    description: str | None = None
    base_branch: str = "test"
    environments: list[str] = Field(default_factory=list)

    repos: dict[str, RepoEntry] = Field(default_factory=dict)

    statuses: list[str] = Field(default_factory=list)
    status_transitions: dict[str, list[str]] = Field(default_factory=dict)

    label_categories: LabelCategories = Field(default_factory=LabelCategories)

    graph: GraphSettings = Field(default_factory=GraphSettings)

    orchestration: OrchestrationConfig = Field(default_factory=OrchestrationConfig)

    next_issue_number: int = 1
    next_session_number: int = 1

    # Workflow phase — drives phase-aware validation checks.
    phase: ProjectPhase = ProjectPhase.scoping

    created_at: datetime | None = None

    # v0.6b: optional workspace link. Absence means standalone project.
    workspace: ProjectWorkspacePointer | None = None

    # Free-form per-project metadata, never used by the package itself.
    metadata: dict[str, Any] = Field(default_factory=dict)
