"""Graph read service — React Flow-shaped dependency + concept graphs.

Wraps :mod:`tripwire.core.graph.dependency` and
:mod:`tripwire.core.graph.concept` to produce JSON payloads matching the
React Flow node+edge schema. Positions are computed server-side with a
deterministic layered layout so the frontend doesn't need a layout
engine.

The layout is **not** full dagre — it's a pure-Python layered BFS that
keeps nodes with no dependencies on the left column and fans rightwards.
It's deterministic (seeded ordering) and fast enough for up to a few
hundred nodes. The execution hint for KUI-17 explicitly allows this
tradeoff; revisit if a graph grows past ~300 nodes.
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from tripwire.core.graph import cache as graph_cache
from tripwire.core.graph.concept import build_full_graph
from tripwire.core.graph.dependency import build_dependency_graph as _core_dep_graph
from tripwire.core.selectors import resolve_selector
from tripwire.core.store import list_issues
from tripwire.models.graph import (
    DependencyGraphResult,
    FullGraphResult,
    GraphEdge,
    GraphNode,
)

logger = logging.getLogger("tripwire.ui.services.graph_service")

# Layout constants — deliberately chosen so the frontend can start
# rendering without re-layouting. Column width must be wide enough for
# a typical issue label.
_LAYER_WIDTH = 260.0
_ROW_HEIGHT = 120.0


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


GraphKind = Literal["deps", "concept"]


class ReactFlowPosition(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    x: float
    y: float


class ReactFlowNode(BaseModel):
    """One node in the React Flow-shaped payload."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    type: str  # React Flow node-type string (e.g. "issue", "concept")
    position: ReactFlowPosition
    data: dict[str, Any] = Field(default_factory=dict)


class ReactFlowEdge(BaseModel):
    """One edge in the React Flow-shaped payload."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    source: str
    target: str
    relation: str  # "blocked_by" | "references" | "related" | "parent" | ...
    data: dict[str, Any] = Field(default_factory=dict)


class GraphMeta(BaseModel):
    """Metadata about how the graph was built."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    kind: GraphKind
    focus: str | None = None
    upstream: bool = False
    downstream: bool = False
    depth: int | None = None
    node_count: int
    edge_count: int
    orphans: list[str] = Field(default_factory=list)


class ReactFlowGraph(BaseModel):
    """Top-level payload served to the frontend."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    nodes: list[ReactFlowNode] = Field(default_factory=list)
    edges: list[ReactFlowEdge] = Field(default_factory=list)
    meta: GraphMeta


# ---------------------------------------------------------------------------
# Layout — deterministic layered BFS
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _LayoutResult:
    positions: dict[str, tuple[float, float]]


def _layered_layout(
    node_ids: list[str],
    edges: list[GraphEdge],
) -> _LayoutResult:
    """Compute deterministic (x, y) positions for every node.

    Algorithm:

    1. Sort node ids so ties break identically across calls.
    2. Compute an in-degree over the given edges (edges are directed
       from_id → to_id).
    3. Assign each node to a layer by Kahn's-style BFS from in-degree
       zero. Nodes in a cycle get collapsed into the earliest layer
       reachable and broken deterministically by id.
    4. Lay out each layer as a column, spacing rows by _ROW_HEIGHT.

    The layout is pure Python, deterministic, and stable across calls
    with identical input (empty position dicts never appear).
    """
    if not node_ids:
        return _LayoutResult(positions={})

    ids_sorted = sorted(node_ids)
    id_set = set(ids_sorted)

    out_adj: dict[str, list[str]] = defaultdict(list)
    in_deg: dict[str, int] = dict.fromkeys(ids_sorted, 0)
    for edge in edges:
        if edge.from_id in id_set and edge.to_id in id_set:
            out_adj[edge.from_id].append(edge.to_id)
            in_deg[edge.to_id] += 1

    for v in out_adj.values():
        v.sort()

    layer_of: dict[str, int] = {}
    queue: deque[str] = deque(nid for nid in ids_sorted if in_deg[nid] == 0)
    for nid in queue:
        layer_of[nid] = 0

    # If every node is in a cycle (no in-degree 0), seed with the
    # lexicographically smallest id so we still produce a layout.
    if not queue:
        seed = ids_sorted[0]
        queue.append(seed)
        layer_of[seed] = 0

    in_deg_work = dict(in_deg)
    while queue:
        current = queue.popleft()
        for successor in out_adj[current]:
            # Successor's layer is at least one deeper than current.
            new_layer = layer_of[current] + 1
            if layer_of.get(successor, -1) < new_layer:
                layer_of[successor] = new_layer
            in_deg_work[successor] -= 1
            if in_deg_work[successor] <= 0 and successor not in queue:
                queue.append(successor)

    # Any node we never reached (isolated cycle component) — assign to 0.
    for nid in ids_sorted:
        layer_of.setdefault(nid, 0)

    by_layer: dict[int, list[str]] = defaultdict(list)
    for nid in ids_sorted:
        by_layer[layer_of[nid]].append(nid)

    positions: dict[str, tuple[float, float]] = {}
    for layer_index in sorted(by_layer):
        rows = by_layer[layer_index]
        # Centre rows vertically around y=0 so the graph is roughly balanced.
        total = len(rows)
        for row_index, nid in enumerate(rows):
            x = float(layer_index) * _LAYER_WIDTH
            y = (row_index - (total - 1) / 2.0) * _ROW_HEIGHT
            positions[nid] = (x, y)

    return _LayoutResult(positions=positions)


# ---------------------------------------------------------------------------
# Graph-shape helpers
# ---------------------------------------------------------------------------


def _react_flow_type_for(graph_node: GraphNode) -> str:
    """Map a GraphNode.kind → React Flow node-type string."""
    if graph_node.kind == "issue":
        return "issue"
    return "concept"


def _react_flow_node(
    node: GraphNode,
    positions: dict[str, tuple[float, float]],
    *,
    has_saved: bool = False,
) -> ReactFlowNode:
    pos = positions.get(node.id, (0.0, 0.0))
    data: dict[str, Any] = {"label": node.label or node.id, "kind": node.kind}
    if node.type is not None:
        data["type"] = node.type
    if node.status is not None:
        data["status"] = node.status
    # Tells the Concept Graph canvas it can skip d3-force seeding for
    # this node — the position came from the persisted YAML layout.
    if has_saved:
        data["has_saved_layout"] = True
    return ReactFlowNode(
        id=node.id,
        type=_react_flow_type_for(node),
        position=ReactFlowPosition(x=pos[0], y=pos[1]),
        data=data,
    )


def _edge_id(edge: GraphEdge, index: int) -> str:
    """Stable id per edge — source→target with the edge type and index.

    The index guarantees uniqueness in the rare case two edges between
    the same nodes share a type (e.g. references + blocked_by are
    already distinct, but belt-and-braces).
    """
    return f"{edge.from_id}:{edge.type}:{edge.to_id}:{index}"


def _react_flow_edges(edges: list[GraphEdge]) -> list[ReactFlowEdge]:
    out: list[ReactFlowEdge] = []
    for i, e in enumerate(edges):
        out.append(
            ReactFlowEdge(
                id=_edge_id(e, i),
                source=e.from_id,
                target=e.to_id,
                relation=e.type,
            )
        )
    return out


def _restrict_to_ids(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    ids: set[str],
) -> tuple[list[GraphNode], list[GraphEdge]]:
    kept_nodes = [n for n in nodes if n.id in ids]
    kept_edges = [e for e in edges if e.from_id in ids and e.to_id in ids]
    return kept_nodes, kept_edges


def _compute_orphans(nodes: list[GraphNode], edges: list[GraphEdge]) -> list[str]:
    connected: set[str] = set()
    for e in edges:
        connected.add(e.from_id)
        connected.add(e.to_id)
    return sorted({n.id for n in nodes} - connected)


# ---------------------------------------------------------------------------
# Public API — dependency graph
# ---------------------------------------------------------------------------


def _resolve_focus(
    project_dir: Path,
    focus: str | None,
    *,
    upstream: bool,
    downstream: bool,
) -> set[str] | None:
    """Return the set of ids to keep, or None for the full graph."""
    if focus is None:
        return None

    if upstream and downstream:
        # Not useful to combine — treat as bare focus, which the selector
        # interprets as the single node (plus no expansion).
        expr = focus
    elif upstream:
        expr = f"+{focus}"
    elif downstream:
        expr = f"{focus}+"
    else:
        expr = focus

    try:
        result = resolve_selector(expr, project_dir)
    except ValueError as exc:
        logger.debug("graph_service: selector %r failed: %s", expr, exc)
        return set()  # empty subgraph rather than the whole thing

    return result.ids


def build_dependency_graph(
    project_dir: Path,
    *,
    focus: str | None = None,
    depth: int | None = None,
    upstream: bool = False,
    downstream: bool = False,
) -> ReactFlowGraph:
    """Build the issue dependency graph (``blocked_by`` edges only).

    Parameters
    ----------
    focus:
        Optional issue key to centre the subgraph on.
    depth:
        Deprecated; kept for API compatibility — the underlying selector
        does not yet accept a depth in this path. Full upstream/downstream
        expansion is the supported semantic.
    upstream:
        With a ``focus``, keep the issue plus everything it references
        transitively.
    downstream:
        With a ``focus``, keep the issue plus everything that references
        it transitively.
    """
    issues = list_issues(project_dir)
    result: DependencyGraphResult = _core_dep_graph(issues)

    nodes: list[GraphNode] = list(result.nodes)
    edges: list[GraphEdge] = list(result.edges)

    focus_ids = _resolve_focus(
        project_dir, focus, upstream=upstream, downstream=downstream
    )
    if focus_ids is not None:
        # The focus selector is computed over the full concept graph,
        # which includes both issues and nodes — restrict to the issue
        # subset.
        issue_ids = {n.id for n in nodes}
        nodes, edges = _restrict_to_ids(nodes, edges, focus_ids & issue_ids)

    layout = _layered_layout([n.id for n in nodes], edges)
    rf_nodes = [_react_flow_node(n, layout.positions) for n in nodes]
    rf_edges = _react_flow_edges(edges)

    return ReactFlowGraph(
        nodes=rf_nodes,
        edges=rf_edges,
        meta=GraphMeta(
            kind="deps",
            focus=focus,
            upstream=upstream,
            downstream=downstream,
            depth=depth,
            node_count=len(rf_nodes),
            edge_count=len(rf_edges),
            orphans=_compute_orphans(nodes, edges),
        ),
    )


# ---------------------------------------------------------------------------
# Public API — concept graph
# ---------------------------------------------------------------------------


def _saved_layouts(project_dir: Path) -> dict[str, tuple[float, float]]:
    """Read persisted (x, y) layouts from the project's layout sidecar.

    Sidecar lives at `.tripwire/concept-layout.json` (see
    `core/concept_layout.py`). On first read after upgrade we lift any
    pre-existing `node.layout` values out of node YAMLs into the sidecar;
    subsequent reads ignore the YAML field. Returns an empty dict when
    the sidecar is missing or corrupt — callers fall back to the layered
    BFS positions.
    """
    from tripwire.core.concept_layout import (
        bootstrap_from_yaml_if_absent,
        load_concept_layouts,
    )

    bootstrap_from_yaml_if_absent(project_dir)
    return load_concept_layouts(project_dir)


def build_concept_graph(
    project_dir: Path,
    *,
    focus: str | None = None,
    upstream: bool = False,
    downstream: bool = False,
) -> ReactFlowGraph:
    """Build the full concept graph (issues + nodes + all edge types).

    Per KUI-104, the canvas remembers per-node `(x, y)` positions across
    reloads via `.tripwire/concept-layout.json`. When a position is in the
    sidecar it overrides the deterministic layered BFS so the canvas
    reuses the user-blessed position from the previous d3-force run
    instead of re-shuffling on every reload.
    """
    result: FullGraphResult = build_full_graph(project_dir)

    nodes: list[GraphNode] = list(result.nodes)
    edges: list[GraphEdge] = list(result.edges)

    focus_ids = _resolve_focus(
        project_dir, focus, upstream=upstream, downstream=downstream
    )
    if focus_ids is not None:
        nodes, edges = _restrict_to_ids(nodes, edges, focus_ids)

    layout = _layered_layout([n.id for n in nodes], edges)
    saved = _saved_layouts(project_dir)
    positions: dict[str, tuple[float, float]] = dict(layout.positions)
    positions.update(saved)
    rf_nodes = [_react_flow_node(n, positions, has_saved=n.id in saved) for n in nodes]
    rf_edges = _react_flow_edges(edges)

    return ReactFlowGraph(
        nodes=rf_nodes,
        edges=rf_edges,
        meta=GraphMeta(
            kind="concept",
            focus=focus,
            upstream=upstream,
            downstream=downstream,
            depth=None,
            node_count=len(rf_nodes),
            edge_count=len(rf_edges),
            orphans=_compute_orphans(nodes, edges),
        ),
    )


# ---------------------------------------------------------------------------
# Cache-version helper (exposed for route-level response caching later)
# ---------------------------------------------------------------------------


def current_cache_version(project_dir: Path) -> str | None:
    """Return the graph cache's last-update timestamp as a version string.

    Routes can use this as an ETag-style cache key for their own
    response caches; we don't cache at the service level here because
    the layout itself is cheap for the graph sizes we target.
    """
    cache = graph_cache.load_index(project_dir)
    if cache is None:
        return None
    ts = cache.last_incremental_update or cache.last_full_rebuild
    return ts.isoformat() if ts is not None else None


__all__ = [
    "GraphMeta",
    "ReactFlowEdge",
    "ReactFlowGraph",
    "ReactFlowNode",
    "ReactFlowPosition",
    "build_concept_graph",
    "build_dependency_graph",
    "current_cache_version",
]
