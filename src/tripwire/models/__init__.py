"""Pydantic data models for tripwire entities.

The models are intentionally permissive about enum-typed fields (using `str`
rather than `StrEnum`) so that projects can customise their enums via
`<project>/enums/<name>.yaml` without forking the package. The default enum
values are still defined as `StrEnum` classes in `enums.py` for type hints,
IDE autocomplete, and as canonical defaults referenced by the validator.

Validation against the active project enums happens in the validator
(see `core/validator.py`), not in the models themselves.
"""

from tripwire.models.comment import Comment
from tripwire.models.enums import (
    AgentState,
    CommentType,
    Executor,
    IssueStatus,
    MessageType,
    NodeStatus,
    NodeType,
    Priority,
    ReEngagementTrigger,
    SessionStatus,
    Verifier,
)
from tripwire.models.graph import (
    EdgeType,
    FreshnessResult,
    FreshnessStatus,
    FullGraphResult,
    GraphEdge,
    GraphIndex,
    GraphNode,
)
from tripwire.models.issue import Issue
from tripwire.models.node import ConceptNode, NodeSource
from tripwire.models.project import (
    GraphSettings,
    LabelCategories,
    OrchestrationConfig,
    ProjectConfig,
    RepoEntry,
)
from tripwire.models.session import (
    AgentSession,
    ArtifactSpec,
    EngagementEntry,
    RepoBinding,
    RuntimeState,
    SessionOrchestration,
)

__all__ = [
    # entities
    "AgentSession",
    # enums
    "AgentState",
    "ArtifactSpec",
    "Comment",
    "CommentType",
    "ConceptNode",
    # graph
    "EdgeType",
    "EngagementEntry",
    "Executor",
    "FreshnessResult",
    "FreshnessStatus",
    "FullGraphResult",
    "GraphEdge",
    "GraphIndex",
    "GraphNode",
    # project sub-models
    "GraphSettings",
    "Issue",
    "IssueStatus",
    "LabelCategories",
    "MessageType",
    "NodeSource",
    "NodeStatus",
    "NodeType",
    "OrchestrationConfig",
    "Priority",
    "ProjectConfig",
    "ReEngagementTrigger",
    "RepoBinding",
    "RepoEntry",
    "RuntimeState",
    "SessionOrchestration",
    "SessionStatus",
    "Verifier",
]
