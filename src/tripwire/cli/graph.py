"""`tripwire graph` — render or query the unified entity graph.

The command is a Click group with three operating modes:

- `tripwire graph render [...flags...]` — render the dependency or
  concept graph as Mermaid / DOT / JSON. This is the historic
  rendering surface. The bare invocation `tripwire graph [...flags...]`
  (no subcommand) keeps working for backwards compat and dispatches
  to `render`.
- `tripwire graph query upstream <id>` — IDs of nodes the given id
  points at across every entity type.
- `tripwire graph query downstream <id>` — IDs of nodes that point
  at the given id across every entity type.

Both query subcommands take canonical edge-kind filters
(``--kind refs,depends_on``) and a transitive-closure depth
(``--distance N``). They read from `core.graph.index.UnifiedIndex`,
which is a thin facade over the cache (`graph/index.yaml`).
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._profiling import profileable
from tripwire.core.graph import index as graph_index
from tripwire.core.graph.cache import ensure_fresh
from tripwire.core.graph.concept import build_full_graph
from tripwire.core.graph.dependency import (
    build_dependency_graph,
    to_dot,
    to_mermaid,
)
from tripwire.core.store import (
    ProjectNotFoundError,
    list_issues,
    load_project,
)

# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------


@click.group(
    name="graph",
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": False},
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--type",
    "graph_type",
    type=click.Choice(["deps", "concept"]),
    default="deps",
    show_default=True,
    help="`deps` = issue dependency graph; `concept` = full concept graph.",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["mermaid", "dot", "json"]),
    default="mermaid",
    show_default=True,
    help="Output format.",
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to this file instead of stdout.",
)
@click.option(
    "--status-filter",
    default=None,
    help="Comma-separated issue statuses to include (default: all).",
)
@click.option(
    "--upstream",
    "upstream_id",
    default=None,
    help="Render-only: limit to nodes upstream of this ID.",
)
@click.option(
    "--downstream",
    "downstream_id",
    default=None,
    help="Render-only: limit to nodes downstream of this ID.",
)
@click.pass_context
def graph_cmd(
    ctx: click.Context,
    project_dir: Path,
    graph_type: str,
    output_format: str,
    output: Path | None,
    status_filter: str | None,
    upstream_id: str | None,
    downstream_id: str | None,
) -> None:
    """Render or query the entity graph for a project."""
    ctx.ensure_object(dict)
    ctx.obj["project_dir"] = project_dir
    if ctx.invoked_subcommand is None:
        # Backwards-compat: bare `tripwire graph [...flags...]` keeps
        # behaving as the rendering command. The render() implementation
        # is shared.
        ctx.invoke(
            render_cmd,
            project_dir=project_dir,
            graph_type=graph_type,
            output_format=output_format,
            output=output,
            status_filter=status_filter,
            upstream_id=upstream_id,
            downstream_id=downstream_id,
        )


# ---------------------------------------------------------------------------
# render subcommand
# ---------------------------------------------------------------------------


@graph_cmd.command(name="render")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--type",
    "graph_type",
    type=click.Choice(["deps", "concept"]),
    default="deps",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["mermaid", "dot", "json"]),
    default="mermaid",
    show_default=True,
)
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
)
@click.option(
    "--status-filter",
    default=None,
)
@click.option(
    "--upstream",
    "upstream_id",
    default=None,
    help="Show only nodes upstream of (depended on by) this ID.",
)
@click.option(
    "--downstream",
    "downstream_id",
    default=None,
    help="Show only nodes downstream of (depending on) this ID.",
)
@profileable
def render_cmd(
    project_dir: Path,
    graph_type: str,
    output_format: str,
    output: Path | None,
    status_filter: str | None,
    upstream_id: str | None,
    downstream_id: str | None,
) -> None:
    """Render the dependency or concept graph for a project.

    The dependency graph (`--type deps`) is the graph of issues
    connected by `blocked_by` relations, with cycle detection and a
    critical path. The concept graph (`--type concept`) is the full
    unified view: issues, concept nodes, and every edge type.
    """
    resolved = project_dir.expanduser().resolve()
    try:
        load_project(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if upstream_id and downstream_id:
        raise click.ClickException("Cannot specify both --upstream and --downstream.")

    rendered = _render(
        resolved,
        graph_type,
        output_format,
        status_filter,
        upstream_id=upstream_id,
        downstream_id=downstream_id,
    )

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        click.echo(rendered, nl=False)


# ---------------------------------------------------------------------------
# query subcommand
# ---------------------------------------------------------------------------


@graph_cmd.group(name="query")
def query_cmd() -> None:
    """Cross-type traversal of the unified entity graph (KUI-133 / A8)."""


def _query_options(func):
    """Shared options for `query upstream` / `query downstream`."""
    func = click.option(
        "--project-dir",
        type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
    )(func)
    func = click.option(
        "--kind",
        "kinds",
        default=None,
        help="Comma-separated canonical edge kinds (refs, depends_on, "
        "implements, produced-by, supersedes, addressed-by, "
        "tripwire-fired-on). Default: every kind.",
    )(func)
    func = click.option(
        "--type",
        "node_types",
        default=None,
        help="Comma-separated canonical node kinds (concept-node, issue, "
        "session, decision, comment, pull-request, tripwire-instance). "
        "Default: every kind.",
    )(func)
    func = click.option(
        "--distance",
        type=int,
        default=1,
        show_default=True,
        help="Maximum edge-hop distance for transitive closure.",
    )(func)
    func = click.option(
        "--format",
        "output_format",
        type=click.Choice(["plain", "json"]),
        default="plain",
        show_default=True,
    )(func)
    return func


@query_cmd.command(name="upstream")
@click.argument("node_id")
@_query_options
def query_upstream(
    node_id: str,
    project_dir: Path,
    kinds: str | None,
    node_types: str | None,
    distance: int,
    output_format: str,
) -> None:
    """IDs of nodes reachable from NODE_ID via outgoing edges."""
    _run_query(
        node_id,
        project_dir=project_dir,
        kinds=kinds,
        node_types=node_types,
        distance=distance,
        direction="upstream",
        output_format=output_format,
    )


@query_cmd.command(name="downstream")
@click.argument("node_id")
@_query_options
def query_downstream(
    node_id: str,
    project_dir: Path,
    kinds: str | None,
    node_types: str | None,
    distance: int,
    output_format: str,
) -> None:
    """IDs of nodes that reach NODE_ID via outgoing edges (incoming)."""
    _run_query(
        node_id,
        project_dir=project_dir,
        kinds=kinds,
        node_types=node_types,
        distance=distance,
        direction="downstream",
        output_format=output_format,
    )


# ---------------------------------------------------------------------------
# Implementation helpers
# ---------------------------------------------------------------------------


def _run_query(
    node_id: str,
    *,
    project_dir: Path,
    kinds: str | None,
    node_types: str | None,
    distance: int,
    direction: str,
    output_format: str,
) -> None:
    resolved = project_dir.expanduser().resolve()
    try:
        load_project(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    # Make sure the cache reflects what's on disk before we read.
    ensure_fresh(resolved)

    idx = graph_index.load(resolved)
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None

    if direction == "upstream":
        ids = idx.upstream(node_id, kinds=kind_list, distance=distance)
    else:
        ids = idx.downstream(node_id, kinds=kind_list, distance=distance)

    if node_types:
        wanted_types = {t.strip() for t in node_types.split(",") if t.strip()}
        ids = [i for i in ids if _node_kind_for(idx, i) in wanted_types]

    payload = {"id": node_id, "direction": direction, "ids": ids}
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2))
    else:
        if not ids:
            click.echo(f"(no {direction} edges for {node_id})")
            return
        for i in ids:
            click.echo(i)


def _node_kind_for(idx: graph_index.UnifiedIndex, node_id: str) -> str | None:
    """Best-effort canonical NodeKind for a known id.

    The unified index doesn't yet carry an explicit node-kind table for
    every entity. We infer from edge source files: an id whose only
    incoming/outgoing edges live under `sessions/` is a session; under
    `issues/.../comments/` is a comment; under `issues/<KEY>/issue.yaml`
    is an issue; under `nodes/` is a concept-node.
    """
    files: set[str] = set()
    for e in idx.edges_into(node_id):
        if e.source_file:
            files.add(e.source_file)
    for e in idx.edges_from(node_id):
        if e.source_file:
            files.add(e.source_file)
    for f in files:
        if f.startswith("sessions/"):
            return "session"
        if "/comments/" in f:
            return "comment"
        if f.startswith("nodes/"):
            return "concept-node"
        if f.startswith("issues/") and f.endswith("/issue.yaml"):
            return "issue"
    return None


# ---------------------------------------------------------------------------
# Render implementation (unchanged from pre-v0.9, refactored for shared use)
# ---------------------------------------------------------------------------


def _bfs_reachable(
    start_id: str,
    adjacency: dict[str, set[str]],
) -> set[str]:
    """BFS from start_id over an adjacency map, returning all reachable IDs
    (including start_id itself)."""
    visited: set[str] = set()
    queue = [start_id]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for neighbour in adjacency.get(current, set()):
            if neighbour not in visited:
                queue.append(neighbour)
    return visited


def _filter_graph_by_direction(
    result: object,
    upstream_id: str | None,
    downstream_id: str | None,
) -> None:
    """Mutate a FullGraphResult in-place to keep only the upstream or
    downstream subgraph of the given ID."""
    if not upstream_id and not downstream_id:
        return

    nodes = result.nodes  # type: ignore[attr-defined]
    edges = result.edges  # type: ignore[attr-defined]
    all_ids = {n.id for n in nodes}
    target_id = upstream_id or downstream_id

    if target_id not in all_ids:
        raise click.ClickException(f"Node '{target_id}' not found in graph.")

    if upstream_id:
        adj: dict[str, set[str]] = {}
        for e in edges:
            adj.setdefault(e.from_id, set()).add(e.to_id)
        keep = _bfs_reachable(upstream_id, adj)
    else:
        adj = {}
        for e in edges:
            adj.setdefault(e.to_id, set()).add(e.from_id)
        keep = _bfs_reachable(downstream_id, adj)  # type: ignore[arg-type]

    result.nodes = [n for n in nodes if n.id in keep]  # type: ignore[attr-defined]
    result.edges = [  # type: ignore[attr-defined]
        e for e in edges if e.from_id in keep and e.to_id in keep
    ]


def _render(
    project_dir: Path,
    graph_type: str,
    output_format: str,
    status_filter: str | None,
    *,
    upstream_id: str | None = None,
    downstream_id: str | None = None,
) -> str:
    if graph_type == "deps":
        issues = list_issues(project_dir)
        if status_filter:
            allowed = {s.strip() for s in status_filter.split(",") if s.strip()}
            issues = [i for i in issues if i.status in allowed]
        result = build_dependency_graph(issues)
        if output_format == "json":
            return (
                json.dumps(result.model_dump(mode="json", by_alias=True), indent=2)
                + "\n"
            )
        if output_format == "dot":
            return to_dot(result)
        return to_mermaid(result)

    # graph_type == "concept"
    result = build_full_graph(project_dir)
    if status_filter:
        allowed = {s.strip() for s in status_filter.split(",") if s.strip()}
        kept_ids = {n.id for n in result.nodes if not n.status or n.status in allowed}
        result.nodes = [n for n in result.nodes if n.id in kept_ids]
        result.edges = [
            e for e in result.edges if e.from_id in kept_ids and e.to_id in kept_ids
        ]
    _filter_graph_by_direction(result, upstream_id, downstream_id)
    if output_format == "json":
        return (
            json.dumps(result.model_dump(mode="json", by_alias=True), indent=2) + "\n"
        )
    if output_format == "dot":
        return _concept_to_dot(result)
    return _concept_to_mermaid(result)


def _concept_to_mermaid(result: object) -> str:
    """Render a FullGraphResult as a Mermaid flowchart."""
    lines = ["graph LR"]
    for node in result.nodes:  # type: ignore[attr-defined]
        label = _mermaid_escape_label(node.label or node.id)
        if node.kind == "node":
            lines.append(f'  {_safe_id(node.id)}(("{label}"))')
        else:
            lines.append(f'  {_safe_id(node.id)}["{label}"]')
    for edge in result.edges:  # type: ignore[attr-defined]
        lines.append(
            f"  {_safe_id(edge.from_id)} -->|{edge.type}| {_safe_id(edge.to_id)}"
        )
    return "\n".join(lines) + "\n"


def _concept_to_dot(result: object) -> str:
    lines = ["digraph concept {", "  rankdir=LR;"]
    for node in result.nodes:  # type: ignore[attr-defined]
        label = (node.label or node.id).replace('"', '\\"')
        shape = "ellipse" if node.kind == "node" else "box"
        lines.append(f'  "{node.id}" [label="{label}", shape={shape}];')
    for edge in result.edges:  # type: ignore[attr-defined]
        lines.append(f'  "{edge.from_id}" -> "{edge.to_id}" [label="{edge.type}"];')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _safe_id(raw: str) -> str:
    """Mermaid node IDs must be alphanumeric + underscore. Replace `-` with `_`."""
    return raw.replace("-", "_").replace(".", "_")


def _mermaid_escape_label(raw: str) -> str:
    out = raw
    out = out.replace('"', "#quot;")
    out = out.replace("\n", "<br/>")
    out = out.replace("[", "(").replace("]", ")")
    return out


__all__ = ["graph_cmd"]
