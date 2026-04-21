"""Selector grammar for subset operations on the concept graph.

Selectors resolve to a set of entity IDs (issues + nodes). Used by
``--select`` flags on ``validate``, ``graph``, ``status``.

Grammar (v0.1 — deliberately simple):

    selector     = node_select | tag_select
    node_select  = ["+" ] ID ["+" [DEPTH]]
    tag_select   = "tag:" TAG_NAME

Examples:
    SEI-42+      downstream: SEI-42 and all referrers (things that reference SEI-42)
    +SEI-42      upstream: SEI-42 and all things SEI-42 references
    SEI-42+2     downstream, max 2 hops
    tag:critical all entities with label "critical"
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from tripwire.core.concept_graph import build_full_graph
from tripwire.models.graph import FullGraphResult


@dataclass
class SelectorResult:
    """The set of entity IDs matched by a selector."""

    ids: set[str]
    selector_expr: str


def _bfs(start: str, adj: dict[str, set[str]], max_depth: int | None) -> set[str]:
    """BFS from start, returning all reachable IDs within max_depth."""
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start, 0)]
    while queue:
        current, depth = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        if max_depth is not None and depth >= max_depth:
            continue
        for neighbour in adj.get(current, set()):
            if neighbour not in visited:
                queue.append((neighbour, depth + 1))
    return visited


# Patterns for parsing
_UPSTREAM_RE = re.compile(r"^\+(.+)$")  # +ID
_DOWNSTREAM_RE = re.compile(r"^([^+]+)\+(\d*)$")  # ID+ or ID+N
_TAG_RE = re.compile(r"^tag:(.+)$")


def resolve_selector(
    expr: str,
    project_dir: Path,
) -> SelectorResult:
    """Parse and evaluate a selector expression against a project."""
    expr = expr.strip()
    graph = build_full_graph(project_dir)
    all_ids = {n.id for n in graph.nodes}

    # tag:X
    m = _TAG_RE.match(expr)
    if m:
        tag = m.group(1)
        return _resolve_tag(tag, graph, expr)

    # +ID (upstream)
    m = _UPSTREAM_RE.match(expr)
    if m:
        target = m.group(1)
        if target not in all_ids:
            raise ValueError(f"Node '{target}' not found in graph.")
        return _resolve_upstream(target, graph, expr)

    # ID+ or ID+N (downstream)
    m = _DOWNSTREAM_RE.match(expr)
    if m:
        target = m.group(1)
        depth_str = m.group(2)
        max_depth = int(depth_str) if depth_str else None
        if target not in all_ids:
            raise ValueError(f"Node '{target}' not found in graph.")
        return _resolve_downstream(target, graph, max_depth, expr)

    # Bare ID — validate just this entity, no expansion
    if expr in all_ids:
        return SelectorResult(ids={expr}, selector_expr=expr)

    raise ValueError(
        f"Invalid selector: {expr!r}. "
        f"Expected: ID (single entity), ID+ (downstream), +ID (upstream), "
        f"ID+N (N hops), tag:NAME"
    )


def _resolve_upstream(target: str, graph: FullGraphResult, expr: str) -> SelectorResult:
    """Upstream = target + everything target references transitively."""
    adj: dict[str, set[str]] = {}
    for e in graph.edges:
        adj.setdefault(e.from_id, set()).add(e.to_id)
    ids = _bfs(target, adj, None)
    return SelectorResult(ids=ids, selector_expr=expr)


def _resolve_downstream(
    target: str, graph: FullGraphResult, max_depth: int | None, expr: str
) -> SelectorResult:
    """Downstream = target + everything that references target transitively."""
    adj: dict[str, set[str]] = {}
    for e in graph.edges:
        adj.setdefault(e.to_id, set()).add(e.from_id)
    ids = _bfs(target, adj, max_depth)
    return SelectorResult(ids=ids, selector_expr=expr)


def _resolve_tag(tag: str, graph: FullGraphResult, expr: str) -> SelectorResult:
    """Tag selector — match nodes by type or issues by label-like matching.

    Since Issue objects aren't in the graph model, we match GraphNode.type.
    """
    ids = {n.id for n in graph.nodes if n.type == tag}
    return SelectorResult(ids=ids, selector_expr=expr)
