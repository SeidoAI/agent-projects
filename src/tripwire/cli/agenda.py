"""`tripwire agenda` — aggregated view of everything in flight.

Reads all issues from the project and renders a unified "what's in
flight" feed, grouped by a chosen axis (status, executor, priority).
This is the "one command, one view" situational-awareness surface.

Output formats:
- `text` (default): rich tables grouped by the chosen axis
- `json`: structured JSON for programmatic consumption and the
  `/pm-agenda` slash command
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.core import graph_cache
from tripwire.core.dependency_graph import build_dependency_graph
from tripwire.core.store import (
    ProjectNotFoundError,
    list_issues,
    load_project,
)

console = Console()


# ============================================================================
# Data model
# ============================================================================


@dataclass
class AgendaItem:
    """One item in the agenda feed."""

    id: str
    title: str
    status: str
    priority: str
    executor: str
    blocked_by: list[str] = field(default_factory=list)
    is_blocked: bool = False
    is_stale: bool = False


@dataclass
class AgendaGroup:
    """A group of items under one axis value (e.g. status=in_progress)."""

    key: str
    items: list[AgendaItem] = field(default_factory=list)


@dataclass
class AgendaResult:
    """The full agenda output."""

    project_name: str
    group_by: str
    total_issues: int
    groups: list[AgendaGroup] = field(default_factory=list)
    blocked_count: int = 0
    stale_count: int = 0
    critical_path: list[str] = field(default_factory=list)


# ============================================================================
# Collection
# ============================================================================


def _collect_agenda(
    project_dir: Path,
    group_by: str,
    filter_expr: str | None,
) -> AgendaResult:
    project = load_project(project_dir)
    issues = list_issues(project_dir)

    # Blocked detection
    id_to_status = {i.id: i.status for i in issues}
    blocked_ids: set[str] = set()
    for issue in issues:
        for blocker in issue.blocked_by:
            # v0.9.4: canonical "completed" + legacy "done" alias.
            if id_to_status.get(blocker) and id_to_status[blocker] not in (
                "completed",
                "done",
            ):
                blocked_ids.add(issue.id)
                break

    # Stale nodes from graph cache
    cache = graph_cache.load_index(project_dir)
    stale_set = set(cache.stale_nodes) if cache else set()

    # Critical path
    dep_graph = build_dependency_graph(issues)
    critical_path = dep_graph.critical_path

    # Optional filter
    if filter_expr:
        key, _, val = filter_expr.partition(":")
        key, val = key.strip(), val.strip()
        if key and val:
            issues = [i for i in issues if getattr(i, key, None) == val]

    # Build agenda items
    items_by_group: dict[str, list[AgendaItem]] = defaultdict(list)
    for issue in issues:
        item = AgendaItem(
            id=issue.id,
            title=issue.title,
            status=issue.status,
            priority=issue.priority,
            executor=issue.executor,
            blocked_by=issue.blocked_by,
            is_blocked=issue.id in blocked_ids,
            is_stale=issue.id in stale_set,
        )
        group_key = getattr(issue, group_by, "unknown")
        items_by_group[group_key].append(item)

    groups = [AgendaGroup(key=k, items=v) for k, v in sorted(items_by_group.items())]

    return AgendaResult(
        project_name=project.name,
        group_by=group_by,
        total_issues=len(issues),
        groups=groups,
        blocked_count=len(blocked_ids),
        stale_count=len(stale_set),
        critical_path=critical_path,
    )


# ============================================================================
# Renderers
# ============================================================================


def _render_text(result: AgendaResult) -> None:
    console.print(
        f"[bold]{result.project_name}[/bold] — "
        f"{result.total_issues} issues "
        f"(grouped by {result.group_by})"
    )
    if result.blocked_count:
        console.print(f"  [yellow]{result.blocked_count} blocked[/yellow]", end="")
    if result.stale_count:
        console.print(f"  [red]{result.stale_count} stale[/red]", end="")
    if result.critical_path:
        console.print(
            f"  [cyan]critical path: {' → '.join(result.critical_path)}[/cyan]",
            end="",
        )
    console.print()

    for group in result.groups:
        table = Table(
            title=f"{result.group_by}: {group.key} ({len(group.items)})",
            show_header=True,
            header_style="bold",
        )
        table.add_column("id", style="bold")
        table.add_column("title")
        table.add_column("priority")
        table.add_column("executor")
        table.add_column("flags", justify="right")
        for item in group.items:
            flags = []
            if item.is_blocked:
                flags.append("[yellow]blocked[/yellow]")
            if item.is_stale:
                flags.append("[red]stale[/red]")
            table.add_row(
                item.id,
                item.title,
                item.priority,
                item.executor,
                " ".join(flags),
            )
        console.print(table)


def _render_json(result: AgendaResult) -> str:
    return json.dumps(asdict(result), indent=2, sort_keys=False)


# ============================================================================
# Click command
# ============================================================================


@click.command(name="agenda")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.option(
    "--by",
    "group_by",
    type=click.Choice(["status", "executor", "priority"]),
    default="status",
    show_default=True,
    help="Axis to group issues by.",
)
@click.option(
    "--filter",
    "filter_expr",
    default=None,
    help="Filter expression (e.g. 'status:in_progress', 'executor:ai').",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def agenda_cmd(
    project_dir: Path,
    group_by: str,
    filter_expr: str | None,
    output_format: str,
) -> None:
    """Aggregated view of everything in flight.

    Groups all issues by the chosen axis (status, executor, priority)
    and shows blocked items, stale nodes, and the critical path.
    """
    resolved = project_dir.expanduser().resolve()
    try:
        result = _collect_agenda(resolved, group_by, filter_expr)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(_render_json(result))
    else:
        _render_text(result)
