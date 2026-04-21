"""`tripwire status` — dashboard summary of a project.

Prints issue counts by status/executor/priority, blocked issues, stale
references (from the graph cache), and the critical path through the
dependency graph. Read-only — no cache rebuild, no file writes.

For a richer long-running UI, this is the same data the web dashboard
would surface. For the CLI, it's a quick "where is this project at?"
view the human or orchestrator can glance at.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.cli._profiling import profileable
from tripwire.core import graph_cache
from tripwire.core.dependency_graph import build_dependency_graph
from tripwire.core.store import (
    ProjectNotFoundError,
    list_issues,
    load_project,
)
from tripwire.models.issue import Issue

console = Console()


@dataclass
class StatusSummary:
    """Structured dashboard data — used for both rich and JSON output."""

    project_name: str
    key_prefix: str
    total_issues: int
    by_status: dict[str, int] = field(default_factory=dict)
    by_executor: dict[str, int] = field(default_factory=dict)
    by_priority: dict[str, int] = field(default_factory=dict)
    blocked_issues: list[str] = field(default_factory=list)
    stale_nodes: list[str] = field(default_factory=list)
    critical_path: list[str] = field(default_factory=list)
    critical_path_length: int = 0


def _collect_status(project_dir: Path) -> StatusSummary:
    """Compute the dashboard data for a project."""
    project = load_project(project_dir)
    issues = list_issues(project_dir)

    by_status = Counter(i.status for i in issues)
    by_executor = Counter(i.executor for i in issues)
    by_priority = Counter(i.priority for i in issues)

    blocked = _blocked_issues(issues)

    cache = graph_cache.load_index(project_dir)
    stale_nodes = cache.stale_nodes if cache is not None else []

    dep_graph = build_dependency_graph(issues)
    critical_path = dep_graph.critical_path

    return StatusSummary(
        project_name=project.name,
        key_prefix=project.key_prefix,
        total_issues=len(issues),
        by_status=dict(by_status),
        by_executor=dict(by_executor),
        by_priority=dict(by_priority),
        blocked_issues=blocked,
        stale_nodes=stale_nodes,
        critical_path=critical_path,
        critical_path_length=len(critical_path),
    )


def _blocked_issues(issues: list[Issue]) -> list[str]:
    """Return issue ids that have at least one unresolved blocker.

    A blocker is "unresolved" if it's an existing issue that is not yet
    `done`. Dangling `blocked_by` entries are ignored here — the validator
    reports them as `ref/blocked_by` errors.
    """
    id_to_status = {i.id: i.status for i in issues}
    blocked: list[str] = []
    for issue in issues:
        for blocker in issue.blocked_by:
            if id_to_status.get(blocker) and id_to_status[blocker] != "done":
                blocked.append(issue.id)
                break
    return sorted(blocked)


# ============================================================================
# Renderers
# ============================================================================


def _render_rich(summary: StatusSummary) -> None:
    """Render the dashboard via `rich.table.Table`."""
    console.print(
        f"[bold]{summary.project_name}[/bold] ({summary.key_prefix}) — "
        f"{summary.total_issues} issues"
    )
    console.print()

    if summary.by_status:
        table = Table(title="By status", show_header=True, header_style="bold")
        table.add_column("status")
        table.add_column("count", justify="right")
        for status, count in sorted(summary.by_status.items()):
            table.add_row(status, str(count))
        console.print(table)

    if summary.by_executor:
        table = Table(title="By executor", show_header=True, header_style="bold")
        table.add_column("executor")
        table.add_column("count", justify="right")
        for executor, count in sorted(summary.by_executor.items()):
            table.add_row(executor, str(count))
        console.print(table)

    if summary.by_priority:
        table = Table(title="By priority", show_header=True, header_style="bold")
        table.add_column("priority")
        table.add_column("count", justify="right")
        # Render priorities in severity order where possible
        priority_order = ("urgent", "high", "medium", "low")
        for p in priority_order:
            if p in summary.by_priority:
                table.add_row(p, str(summary.by_priority[p]))
        # Anything else (custom priorities) afterwards
        for p, c in sorted(summary.by_priority.items()):
            if p not in priority_order:
                table.add_row(p, str(c))
        console.print(table)

    console.print()
    blocked_label = (
        f"[yellow]{len(summary.blocked_issues)} blocked[/yellow]"
        if summary.blocked_issues
        else "[green]0 blocked[/green]"
    )
    stale_label = (
        f"[red]{len(summary.stale_nodes)} stale nodes[/red]"
        if summary.stale_nodes
        else "[green]0 stale nodes[/green]"
    )
    critical_label = (
        f"[cyan]critical path: {summary.critical_path_length}[/cyan]"
        if summary.critical_path_length
        else "[dim]no critical path[/dim]"
    )
    console.print(f"  {blocked_label}   {stale_label}   {critical_label}")

    if summary.blocked_issues:
        console.print(
            f"  [dim]blocked: {', '.join(summary.blocked_issues[:10])}"
            + ("…" if len(summary.blocked_issues) > 10 else "")
            + "[/dim]"
        )
    if summary.critical_path:
        console.print(
            f"  [dim]critical path: {' → '.join(summary.critical_path)}[/dim]"
        )


def _render_json(summary: StatusSummary) -> str:
    return json.dumps(asdict(summary), indent=2, sort_keys=False)


# ============================================================================
# Click command
# ============================================================================


@click.command(name="status")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
@profileable
def status_cmd(project_dir: Path, output_format: str) -> None:
    """Dashboard summary of issues, blocked, stale refs, critical path."""
    resolved = project_dir.expanduser().resolve()
    try:
        summary = _collect_status(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(_render_json(summary))
    else:
        _render_rich(summary)
