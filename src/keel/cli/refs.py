"""`keel refs` — reference inspection.

Three subcommands, all read-only:
- `refs list <issue-key>` — show every `[[reference]]` in this issue with
  a resolve + freshness indicator
- `refs reverse <node-id>` — show every issue or node that references
  this node
- `refs check` — full scan across the project, report dangling refs,
  orphan nodes, and stale content hashes

All three read from the graph cache when it exists and fall back to a
filesystem scan otherwise.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from keel.cli._utils import require_project as _require_project
from keel.core import graph_cache
from keel.core.node_store import list_nodes, node_exists
from keel.core.reference_parser import extract_references
from keel.core.store import (
    issue_exists,
    list_issues,
    load_issue,
)

console = Console()


@click.group(name="refs")
def refs_cmd() -> None:
    """Reference inspection (list, reverse, check, summary)."""


# ============================================================================
# refs list
# ============================================================================


@refs_cmd.command("list")
@click.argument("issue_key")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def refs_list(issue_key: str, project_dir: Path, output_format: str) -> None:
    """List the `[[references]]` in ISSUE_KEY with resolve + freshness."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        issue = load_issue(resolved, issue_key)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    refs = list(dict.fromkeys(extract_references(issue.body)))
    rows = []
    for ref in refs:
        exists = node_exists(resolved, ref) or issue_exists(resolved, ref)
        resolves_as = (
            "node"
            if node_exists(resolved, ref)
            else "issue"
            if issue_exists(resolved, ref)
            else "(dangling)"
        )
        rows.append({"ref": ref, "resolves": resolves_as, "exists": exists})

    if output_format == "json":
        click.echo(json.dumps({"issue": issue_key, "references": rows}, indent=2))
        return

    if not rows:
        console.print(f"[dim]{issue_key} has no references[/dim]")
        return
    table = Table(title=f"References in {issue_key}", show_header=True)
    table.add_column("ref")
    table.add_column("resolves")
    table.add_column("status")
    for row in rows:
        status = "[green]ok[/green]" if row["exists"] else "[red]dangling[/red]"
        # Escape `[` for rich markup — `[[ref]]` would otherwise be parsed
        # as markup and the content eaten.
        rendered_ref = f"\\[\\[{row['ref']}]]"
        table.add_row(rendered_ref, row["resolves"], status)
    console.print(table)


# ============================================================================
# refs reverse
# ============================================================================


@refs_cmd.command("reverse")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def refs_reverse(node_id: str, project_dir: Path, output_format: str) -> None:
    """Show every issue or node that references NODE_ID."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    # Prefer the cache — O(1) lookup.
    cache = graph_cache.load_index(resolved)
    if cache is not None and node_id in cache.referenced_by:
        referencing = list(cache.referenced_by[node_id])
    else:
        # Fall back to a scan.
        referencing = []
        for issue in list_issues(resolved):
            if node_id in extract_references(issue.body):
                referencing.append(issue.id)
        for node in list_nodes(resolved):
            if node.id == node_id:
                continue
            if node_id in node.related or node_id in extract_references(node.body):
                referencing.append(node.id)
        referencing = sorted(set(referencing))

    if output_format == "json":
        click.echo(
            json.dumps({"node": node_id, "referenced_by": referencing}, indent=2)
        )
        return

    if not referencing:
        console.print(f"[dim]nothing references \\[\\[{node_id}]][/dim]")
        return
    table = Table(title=f"Referenced by \\[\\[{node_id}]]", show_header=True)
    table.add_column("entity")
    for entity in referencing:
        table.add_row(entity)
    console.print(table)


# ============================================================================
# refs check
# ============================================================================


@dataclass
class RefsCheckReport:
    """Result of `refs check` — grouped findings across the whole project."""

    dangling: list[dict[str, str]] = field(default_factory=list)
    orphan_nodes: list[str] = field(default_factory=list)
    orphan_issues: list[str] = field(default_factory=list)
    stale_nodes: list[str] = field(default_factory=list)


@refs_cmd.command("check")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def refs_check(project_dir: Path, output_format: str) -> None:
    """Full scan: dangling refs, orphan nodes/issues, stale content hashes.

    Exits non-zero when integrity errors are found (dangling refs or stale
    nodes) so callers (CI, pre-commit, verification checklists) can fail
    fast. Orphan nodes/issues are informational, not errors — they exit 0.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    report = _collect_refs_check(resolved)

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "dangling": report.dangling,
                    "orphan_nodes": report.orphan_nodes,
                    "orphan_issues": report.orphan_issues,
                    "stale_nodes": report.stale_nodes,
                },
                indent=2,
            )
        )
    else:
        _render_refs_check(report)

    # Integrity errors fail the command; orphans are informational.
    if report.dangling or report.stale_nodes:
        raise click.exceptions.Exit(1)


def _collect_refs_check(project_dir: Path) -> RefsCheckReport:
    from keel.core.concept_graph import (
        orphan_issues as concept_orphan_issues,
    )
    from keel.core.concept_graph import (
        orphan_nodes as concept_orphan_nodes,
    )

    report = RefsCheckReport()
    issues = list_issues(project_dir)
    nodes = list_nodes(project_dir)
    issue_ids = {i.id for i in issues}
    node_ids = {n.id for n in nodes}

    for issue in issues:
        for ref in extract_references(issue.body):
            if ref not in node_ids and ref not in issue_ids:
                report.dangling.append(
                    {"from": issue.id, "ref": ref, "source": "issue_body"}
                )
    for node in nodes:
        for ref in extract_references(node.body):
            if ref not in node_ids and ref not in issue_ids:
                report.dangling.append(
                    {"from": node.id, "ref": ref, "source": "node_body"}
                )
        for related in node.related:
            if related not in node_ids:
                report.dangling.append(
                    {"from": node.id, "ref": related, "source": "related"}
                )

    report.orphan_nodes = concept_orphan_nodes(project_dir)
    report.orphan_issues = concept_orphan_issues(project_dir)

    cache = graph_cache.load_index(project_dir)
    report.stale_nodes = list(cache.stale_nodes) if cache else []

    return report


def _render_refs_check(report: RefsCheckReport) -> None:
    if report.dangling:
        table = Table(
            title=f"Dangling references ({len(report.dangling)})",
            show_header=True,
        )
        table.add_column("from")
        table.add_column("ref")
        table.add_column("source")
        for item in report.dangling:
            table.add_row(item["from"], f"[[{item['ref']}]]", item["source"])
        console.print(table)
    else:
        console.print("[green]✓ no dangling references[/green]")

    if report.orphan_nodes:
        console.print(
            f"\n[yellow]{len(report.orphan_nodes)} orphan node(s):[/yellow] "
            + ", ".join(report.orphan_nodes)
        )
    else:
        console.print("[green]✓ no orphan nodes[/green]")

    if report.orphan_issues:
        console.print(
            f"\n[yellow]{len(report.orphan_issues)} orphan issue(s):[/yellow] "
            + ", ".join(report.orphan_issues)
        )
    else:
        console.print("[green]✓ no orphan issues[/green]")

    if report.stale_nodes:
        console.print(
            f"\n[red]{len(report.stale_nodes)} stale node(s):[/red] "
            + ", ".join(report.stale_nodes)
        )
    else:
        console.print("[green]✓ no stale nodes[/green]")


# ============================================================================
# refs summary
# ============================================================================


@refs_cmd.command("summary")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def refs_summary(project_dir: Path, output_format: str) -> None:
    """Per-node reference counts across the project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    nodes = list_nodes(resolved)
    issues = list_issues(resolved)
    node_ids = {n.id for n in nodes}

    # Count referrers per node
    ref_counts: dict[str, list[str]] = {nid: [] for nid in sorted(node_ids)}
    for issue in issues:
        for ref in set(extract_references(issue.body)):
            if ref in ref_counts:
                ref_counts[ref].append(issue.id)
    for node in nodes:
        for ref in set(extract_references(node.body)):
            if ref in ref_counts and ref != node.id:
                ref_counts[ref].append(node.id)
        for related in node.related:
            if related in ref_counts and related != node.id:
                if node.id not in ref_counts[related]:
                    ref_counts[related].append(node.id)

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    nid: {"count": len(refs), "referrers": sorted(refs)}
                    for nid, refs in sorted(ref_counts.items())
                },
                indent=2,
            )
        )
        return

    if not ref_counts:
        console.print("[dim]no concept nodes found[/dim]")
        return

    table = Table(title="Node reference summary", show_header=True)
    table.add_column("node")
    table.add_column("refs", justify="right")
    table.add_column("referrers")
    for nid, refs in sorted(ref_counts.items(), key=lambda x: len(x[1])):
        count = len(refs)
        style = "red" if count == 0 else "yellow" if count == 1 else ""
        referrers = ", ".join(sorted(refs)[:5])
        if len(refs) > 5:
            referrers += f" (+{len(refs) - 5} more)"
        table.add_row(
            f"[{style}]{nid}[/{style}]" if style else nid,
            f"[{style}]{count}[/{style}]" if style else str(count),
            referrers,
        )
    console.print(table)


# ============================================================================
# Helpers
# ============================================================================
