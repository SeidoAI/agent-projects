"""`tripwire graph` — render the dependency or concept graph.

Thin CLI wrapper over `core.dependency_graph` and `core.concept_graph`.
Reads from the cache (`graph/index.yaml`) when available, falls back to
a filesystem scan otherwise.

Output formats:
- `mermaid` (default) — `graph LR` flowchart for the Mermaid renderer
- `dot` — Graphviz DOT
- `json` — the computed graph as JSON (for the UI and programmatic use)
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._profiling import profileable
from tripwire.core.concept_graph import build_full_graph
from tripwire.core.dependency_graph import (
    build_dependency_graph,
    to_dot,
    to_mermaid,
)
from tripwire.core.store import (
    ProjectNotFoundError,
    list_issues,
    load_project,
)


@click.command(name="graph")
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
    help="Output format. JSON is available for programmatic consumers.",
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
    help="Show only nodes upstream of (depended on by) this ID.",
)
@click.option(
    "--downstream",
    "downstream_id",
    default=None,
    help="Show only nodes downstream of (depending on) this ID.",
)
@profileable
def graph_cmd(
    project_dir: Path,
    graph_type: str,
    output_format: str,
    output: Path | None,
    status_filter: str | None,
    upstream_id: str | None,
    downstream_id: str | None,
) -> None:
    """Render the dependency or concept graph for a project.

    The dependency graph (`--type deps`) is the graph of issues connected
    by `blocked_by` relations, with cycle detection and a critical path.
    The concept graph (`--type concept`) is the full unified view: issues,
    concept nodes, and every edge type.
    """
    resolved = project_dir.expanduser().resolve()
    try:
        load_project(resolved)  # validates project.yaml is present
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

    # Edge direction convention: `from_id -> to_id` means from_id *depends
    # on* / *references* to_id (the source depends on the target).
    #
    #   --upstream X:   the things X depends on. Follow the outgoing
    #                   edges of X (the forward adjacency): X -> to_id.
    #   --downstream X: the things that depend on X. Follow the incoming
    #                   edges of X (the reverse adjacency): from_id -> X.
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
    """Render a FullGraphResult as a Mermaid flowchart.

    Concept nodes are rendered as rounded shapes, issues as rectangles.
    The rendering is intentionally simple — the UI's React Flow view is
    where the pretty layout lives.
    """
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
    """Render a FullGraphResult as Graphviz DOT."""
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
    """Make a string safe to sit inside `["..."]` or `(("..."))` in Mermaid.

    Mermaid v10+ supports `#quot;` as an HTML entity for a literal double
    quote inside a quoted label; any other character with semantic meaning
    (`[`, `]`, `(`, `)`) can confuse the older parser, so we replace them
    with visually-similar alternatives rather than escape them. Newlines
    become `<br/>` (Mermaid's in-label break).
    """
    out = raw
    out = out.replace('"', "#quot;")
    out = out.replace("\n", "<br/>")
    out = out.replace("[", "(").replace("]", ")")
    return out
