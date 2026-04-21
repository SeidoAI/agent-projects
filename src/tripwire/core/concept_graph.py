"""Full unified concept graph: issues + nodes + all edges.

This module builds a `FullGraphResult` for UI rendering and reporting. In
v0 it reads directly from the graph cache (`graph/index.yaml`) for speed
and falls back to scanning the project if the cache is missing.

The UI's `/api/projects/:id/graph/concept` endpoint sits directly on top of
this, and the CLI `tripwire graph --type concept` uses it too.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core import graph_cache, paths
from tripwire.core.node_store import list_nodes
from tripwire.core.store import list_issues
from tripwire.models.graph import (
    FullGraphResult,
    GraphEdge,
    GraphIndex,
    GraphNode,
)


def build_full_graph(project_dir: Path) -> FullGraphResult:
    """Build the complete concept graph for a project.

    Prefers the cache. If the cache is missing, falls back to a scan.
    """
    cache = graph_cache.load_index(project_dir)
    if cache is not None:
        return _from_cache(cache, project_dir)
    return _from_scan(project_dir)


def _from_cache(cache: GraphIndex, project_dir: Path) -> FullGraphResult:
    """Build a FullGraphResult directly from a loaded GraphIndex."""
    nodes: list[GraphNode] = []
    node_ids: set[str] = set()

    # Issue files → GraphNode(kind="issue"). Issues live at
    # `issues/<KEY>/issue.yaml`, so the key is the parent dir name.
    for rel, _fp in cache.files.items():
        issue_id = graph_cache.issue_key_from_rel_path(rel)
        if issue_id is None:
            continue
        node_ids.add(issue_id)
        # Read title from the issue file for the graph label
        label = None
        issue_path = project_dir / rel
        if issue_path.is_file():
            try:
                from tripwire.core.parser import parse_frontmatter_body

                fm, _ = parse_frontmatter_body(issue_path.read_text(encoding="utf-8"))
                label = fm.get("title")
            except Exception:
                pass
        nodes.append(GraphNode(id=issue_id, kind="issue", label=label))

    # Node files → GraphNode(kind="node"). We need name/type/status from the
    # file to populate the display fields; we read the file here (still
    # cheaper than a full scan because the cache gave us the exact file set).
    for rel, _fp in cache.files.items():
        node_id = graph_cache.node_id_from_rel_path(rel)
        if node_id is None:
            continue
        parsed = graph_cache._load_node_file(project_dir, rel)
        if parsed is None:
            continue
        node_model, _ = parsed
        node_ids.add(node_id)
        nodes.append(
            GraphNode(
                id=node_id,
                kind="node",
                label=node_model.name,
                type=node_model.type,
                status=node_model.status,
            )
        )

    edges = list(cache.edges)

    orphans = _compute_orphans(node_ids, edges)
    return FullGraphResult(nodes=nodes, edges=edges, orphans=orphans)


def _from_scan(project_dir: Path) -> FullGraphResult:
    """Fallback: scan issues + nodes directly when no cache is available.

    Emits the same set of edges the cache would produce, but does so with a
    full filesystem walk. Only used when `graph/index.yaml` is missing and
    the caller hasn't (yet) run `ensure_fresh` to create it.
    """
    issues = list_issues(project_dir) if paths.issues_dir(project_dir).is_dir() else []
    nodes_list = (
        list_nodes(project_dir) if paths.nodes_dir(project_dir).is_dir() else []
    )

    graph_nodes: list[GraphNode] = [
        GraphNode(id=i.id, kind="issue", label=i.title, status=i.status) for i in issues
    ]
    graph_nodes.extend(
        GraphNode(
            id=n.id,
            kind="node",
            label=n.name,
            type=n.type,
            status=n.status,
        )
        for n in nodes_list
    )

    edges: list[GraphEdge] = []
    from tripwire.core.graph_cache import _issue_edges, _node_edges

    for issue in issues:
        rel = f"{paths.ISSUES_DIR}/{issue.id}/{paths.ISSUE_FILENAME}"
        edges.extend(_issue_edges(issue, rel, issue.body))
    for node in nodes_list:
        rel = f"{paths.NODES_DIR}/{node.id}.yaml"
        edges.extend(_node_edges(node, rel, node.body))

    all_ids = {gn.id for gn in graph_nodes}
    orphans = _compute_orphans(all_ids, edges)
    return FullGraphResult(nodes=graph_nodes, edges=edges, orphans=orphans)


def _compute_orphans(all_ids: set[str], edges: list[GraphEdge]) -> list[str]:
    """Return ids that have no incoming AND no outgoing edges.

    Orphans are typically a signal of a coherence gap — a concept node that
    no issue references, or an issue that has no dependencies and isn't
    referenced anywhere. The UI surfaces them as a warning; the CLI can
    list them with `tripwire refs check`.
    """
    connected: set[str] = set()
    for edge in edges:
        connected.add(edge.from_id)
        connected.add(edge.to_id)
    return sorted(all_ids - connected)


def orphan_nodes(project_dir: Path) -> list[str]:
    """Convenience: return orphan concept nodes only."""
    result = build_full_graph(project_dir)
    orphan_set = set(result.orphans)
    return sorted(n.id for n in result.nodes if n.kind == "node" and n.id in orphan_set)


def orphan_issues(project_dir: Path) -> list[str]:
    """Convenience: return orphan issues only."""
    result = build_full_graph(project_dir)
    orphan_set = set(result.orphans)
    return sorted(
        n.id for n in result.nodes if n.kind == "issue" and n.id in orphan_set
    )
