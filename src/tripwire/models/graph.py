"""Graph models — the cache schema and computed graph results.

The cache (`<project>/graph/index.yaml`) is committed to git and incrementally
updated by `tripwire validate`. Reads of the graph (UI, CLI, agent) go
through the cache for O(1) lookups instead of rescanning every file.

The cache is a derived view; deleting it always rebuilds correctly from the
underlying files.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EdgeType(StrEnum):
    """Legacy edge type strings preserved for on-disk YAML compatibility.

    These are the strings actually written into `graph/index.yaml`. v0.9's
    canonical taxonomy lives on :class:`EdgeKind`; the unified-index facade
    in `core.graph.index` translates between them.
    """

    REFERENCES = "references"  # issue body [[node-id]] → node
    BLOCKED_BY = "blocked_by"  # issue → issue (frontmatter)
    BLOCKS = "blocks"  # inverse of blocked_by, computed
    IMPLEMENTS = "implements"  # issue → requirement (frontmatter)
    PARENT = "parent"  # issue → parent epic (frontmatter)
    RELATED = "related"  # node → node (frontmatter)
    SOURCE = "source"  # node → file location (frontmatter)


class EdgeKind(StrEnum):
    """The 7 canonical edge kinds in the v0.9 unified entity graph.

    Each maps to one or more legacy :class:`EdgeType` strings via
    `core.graph.index.canonical_kind`. New edge writers should emit
    canonical kinds; legacy on-disk strings keep loading via the mapping.
    """

    REFS = "refs"  # body or related references (bidir)
    DEPENDS_ON = "depends_on"  # blockers, prerequisites
    IMPLEMENTS = "implements"  # issue → requirement
    PRODUCED_BY = "produced-by"  # entity → its author/producer
    SUPERSEDES = "supersedes"  # versioned replacement
    ADDRESSED_BY = "addressed-by"  # need / want → solution
    TRIPWIRE_FIRED_ON = "tripwire-fired-on"  # tripwire instance → entity


class NodeKind(StrEnum):
    """The 7 canonical entity types carried as nodes in the unified index."""

    CONCEPT_NODE = "concept-node"
    ISSUE = "issue"
    SESSION = "session"
    DECISION = "decision"
    COMMENT = "comment"
    PULL_REQUEST = "pull-request"
    TRIPWIRE_INSTANCE = "tripwire-instance"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    SOURCE_MISSING = "source_missing"
    NO_SOURCE = "no_source"


class FreshnessResult(BaseModel):
    """Result of checking one node's freshness."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    status: FreshnessStatus
    detail: str | None = None
    current_hash: str | None = None
    stored_hash: str | None = None


class FileFingerprint(BaseModel):
    """Per-file fingerprint stored in the graph cache.

    Used by `update_cache_for_file` to detect what is stale on incremental
    update. The `references_to`, `blocked_by`, and `related` lists let the
    cache rebuild outgoing edges for one file without rescanning everything.
    """

    model_config = ConfigDict(extra="forbid")

    mtime: float
    sha: str
    references_to: list[str] = Field(default_factory=list)
    blocked_by: list[str] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    parent: str | None = None


class GraphEdge(BaseModel):
    """One edge in the computed graph.

    Uses aliases (`from`, `to`) for the YAML keys because `from` is a Python
    keyword. Set `by_alias=True` when dumping to a dict for serialisation.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_id: str = Field(alias="from")
    to_id: str = Field(alias="to")
    type: str
    source_file: str | None = None  # which file this edge came from

    # v0.9 (KUI-131): per-edge provenance for the unified index.
    # `via_artifact` names the file or other artifact that produced this
    # edge (typically the same as `source_file`, but can differ for
    # synthesized edges). `line` pins the line number for body refs so
    # the UI can deep-link back to the prose that introduced the edge.
    via_artifact: str | None = None
    line: int | None = None


class GraphNode(BaseModel):
    """One node in the computed graph (issues + concept nodes both)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str  # "issue" | "node"
    label: str | None = None
    type: str | None = None  # for concept nodes; for issues this is None
    status: str | None = None


class GraphIndex(BaseModel):
    """The cache committed to `<project>/graph/index.yaml`.

    This is a derived view of the underlying files. Deleting it and running
    `tripwire validate` always rebuilds it correctly. The cache is
    purely a performance layer; the source of truth is the issue and node
    files themselves.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = 2
    last_full_rebuild: datetime | None = None
    last_incremental_update: datetime | None = None

    files: dict[str, FileFingerprint] = Field(default_factory=dict)

    by_name: dict[str, str] = Field(default_factory=dict)
    by_type: dict[str, list[str]] = Field(default_factory=dict)
    referenced_by: dict[str, list[str]] = Field(default_factory=dict)

    edges: list[GraphEdge] = Field(default_factory=list)

    stale_nodes: list[str] = Field(default_factory=list)
    last_freshness_check: datetime | None = None


class FullGraphResult(BaseModel):
    """A complete computed graph, returned by `core.concept_graph.build_full_graph`.

    Distinct from `GraphIndex` in that this is the in-memory result for one
    query, not the persisted cache.
    """

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    orphans: list[str] = Field(default_factory=list)


class DependencyGraphResult(BaseModel):
    """Result of `core.dependency_graph.build_dependency_graph`."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    cycles: list[list[str]] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
