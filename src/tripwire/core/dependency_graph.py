"""Issue dependency graph: cycle detection, critical path, Mermaid rendering.

Takes a `list[Issue]` and produces a `DependencyGraphResult` with computed
nodes, edges, cycles, and critical path. The inputs are the raw model
objects, not the cache — this module is usable independently of the graph
cache and is the computational layer the UI and CLI both sit on top of.

The only edge type considered here is `blocked_by` — "A is blocked by B"
produces an edge A → B. Concept-graph edges (references, related) are not
included because they are not dependencies.
"""

from __future__ import annotations

from tripwire.models.graph import (
    DependencyGraphResult,
    GraphEdge,
    GraphNode,
)
from tripwire.models.issue import Issue


def build_dependency_graph(issues: list[Issue]) -> DependencyGraphResult:
    """Build a DependencyGraphResult from a list of issues.

    The resulting graph has one node per issue and one edge per `blocked_by`
    relation. Cycles and critical path are computed on top.
    """
    nodes = [
        GraphNode(
            id=issue.id,
            kind="issue",
            label=issue.title,
            type=None,
            status=issue.status,
        )
        for issue in issues
    ]
    issue_ids = {issue.id for issue in issues}

    edges: list[GraphEdge] = []
    for issue in issues:
        for blocker in issue.blocked_by:
            # Skip edges to unknown issues — the validator catches those
            # as `ref/blocked_by` errors; this module is forgiving.
            if blocker not in issue_ids:
                continue
            edges.append(
                GraphEdge(
                    from_id=issue.id,
                    to_id=blocker,
                    type="blocked_by",
                )
            )

    cycles = _detect_cycles(issue_ids, edges)
    critical_path = _compute_critical_path(issue_ids, edges)

    return DependencyGraphResult(
        nodes=nodes,
        edges=edges,
        cycles=cycles,
        critical_path=critical_path,
    )


def _build_adjacency(ids: set[str], edges: list[GraphEdge]) -> dict[str, list[str]]:
    """Build an adjacency map from a list of edges.

    Maps `from_id → [to_id, ...]`. Returns entries for every id even if no
    outgoing edges, so DFS can walk over an empty neighbour list.
    """
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for edge in edges:
        if edge.from_id in adj and edge.to_id in adj:
            adj[edge.from_id].append(edge.to_id)
    return adj


def _detect_cycles(ids: set[str], edges: list[GraphEdge]) -> list[list[str]]:
    """Find simple cycles via DFS with recursion stack tracking.

    Returns a list of cycles, where each cycle is a list of ids in the
    order they appear on the path. The implementation is iterative to
    avoid Python recursion limits on pathological graphs.
    """
    adj = _build_adjacency(ids, edges)
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(ids, WHITE)

    def _canonical(cycle: list[str]) -> tuple[str, ...]:
        # Rotate the cycle so it starts at its lexicographically smallest
        # element, so "A → B → A" and "B → A → B" are treated as the same.
        if not cycle:
            return ()
        i = min(range(len(cycle)), key=lambda k: cycle[k])
        return tuple(cycle[i:] + cycle[:i])

    for start in sorted(ids):
        if color[start] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = []
        while stack:
            node, idx = stack[-1]
            if idx == 0:
                color[node] = GRAY
                path.append(node)
            neighbours = adj[node]
            if idx < len(neighbours):
                stack[-1] = (node, idx + 1)
                nxt = neighbours[idx]
                if color[nxt] == GRAY:
                    # Found a back-edge → extract the cycle
                    try:
                        start_idx = path.index(nxt)
                    except ValueError:
                        continue
                    cycle = path[start_idx:]
                    canonical = _canonical(cycle)
                    if canonical not in seen_cycles:
                        seen_cycles.add(canonical)
                        cycles.append(list(canonical))
                elif color[nxt] == WHITE:
                    stack.append((nxt, 0))
            else:
                color[node] = BLACK
                path.pop()
                stack.pop()

    return cycles


def _compute_critical_path(ids: set[str], edges: list[GraphEdge]) -> list[str]:
    """Compute the longest chain of dependencies through the DAG.

    For issues, "longest" means the most hops — we don't have durations, so
    every edge has weight 1. Returns an empty list if there are cycles (no
    well-defined longest path) or no issues.

    The returned path is in EXECUTION order: the deepest blocker first,
    ending with the most-dependent issue. For an issue chain
    `TST-3 blocked_by TST-2 blocked_by TST-1`, the edges go
    `TST-3 → TST-2 → TST-1`, the longest graph-walk path ends at TST-1,
    and the execution order is `[TST-1, TST-2, TST-3]`.
    """
    if not ids:
        return []
    if _detect_cycles(ids, edges):
        return []

    from collections import deque

    adj = _build_adjacency(ids, edges)

    # In-degree of each node = count of edges pointing AT it. In our graph
    # edges go dependent → blocker, so high in-degree means "many things
    # depend on me".
    in_deg: dict[str, int] = dict.fromkeys(ids, 0)
    for edge in edges:
        if edge.from_id in in_deg and edge.to_id in in_deg:
            in_deg[edge.to_id] += 1

    # Kahn's topological sort. Starts with nodes that nothing depends on
    # (in_deg 0), ends with leaf blockers (no one depends on them).
    queue: deque[str] = deque(sorted(i for i, d in in_deg.items() if d == 0))
    topo: list[str] = []
    in_deg_work = dict(in_deg)
    while queue:
        current = queue.popleft()
        topo.append(current)
        for successor in adj[current]:
            in_deg_work[successor] -= 1
            if in_deg_work[successor] == 0:
                queue.append(successor)

    # Longest-path DP over the topo order. When we process node i, we
    # relax every one of i's outgoing edges: length[successor] = max(
    # length[successor], length[i] + 1).
    length: dict[str, int] = dict.fromkeys(ids, 1)
    parent: dict[str, str | None] = dict.fromkeys(ids)
    for i in topo:
        for successor in adj[i]:
            if length[i] + 1 > length[successor]:
                length[successor] = length[i] + 1
                parent[successor] = i

    # The endpoint of the longest chain is the node with the greatest length.
    # In our graph direction (dependent → blocker), this is the deepest
    # blocker — the thing that must be done FIRST in execution order.
    endpoint = max(ids, key=lambda i: length[i])

    # Walk back via parents. Each parent was assigned because "successor
    # depends on parent" — so walking parents visits successors first, then
    # their dependencies. That's execution order in reverse, so do NOT
    # reverse again before returning... wait, walking parents FROM the
    # endpoint (the deepest blocker) upward actually visits the endpoint
    # first, then its dependent, then its dependent-dependent. That's
    # execution order as-is.
    path: list[str] = []
    cursor: str | None = endpoint
    while cursor is not None:
        path.append(cursor)
        cursor = parent[cursor]
    return path


# ============================================================================
# Mermaid rendering
# ============================================================================


_STATUS_COLORS = {
    "backlog": "#cccccc",
    "todo": "#9cb3ff",
    "in_progress": "#ffd866",
    "in_review": "#c792ea",
    "verified": "#a9dc76",
    "done": "#7bed9f",
    "canceled": "#777777",
}


def to_mermaid(result: DependencyGraphResult) -> str:
    """Render a DependencyGraphResult as a Mermaid flowchart."""
    lines = ["graph LR"]
    for node in result.nodes:
        label = (node.label or node.id).replace('"', "'")
        lines.append(f'  {node.id}["{node.id}: {label}"]')

    for edge in result.edges:
        lines.append(f"  {edge.from_id} --> {edge.to_id}")

    # Status-based coloring
    status_classes: dict[str, list[str]] = {}
    for node in result.nodes:
        if node.status:
            status_classes.setdefault(node.status, []).append(node.id)

    for status, ids in status_classes.items():
        color = _STATUS_COLORS.get(status, "#dddddd")
        class_name = f"status_{status}"
        lines.append(f"  classDef {class_name} fill:{color}")
        lines.append(f"  class {','.join(ids)} {class_name}")

    return "\n".join(lines) + "\n"


def to_dot(result: DependencyGraphResult) -> str:
    """Render a DependencyGraphResult as Graphviz DOT."""
    lines = ["digraph dependencies {", "  rankdir=LR;"]
    for node in result.nodes:
        label = (node.label or node.id).replace('"', "'")
        lines.append(f'  "{node.id}" [label="{node.id}\\n{label}"];')
    for edge in result.edges:
        lines.append(f'  "{edge.from_id}" -> "{edge.to_id}";')
    lines.append("}")
    return "\n".join(lines) + "\n"
