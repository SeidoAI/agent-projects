"""`tripwire node check` — concept node freshness check.

The only `node` subcommand in v0 is `check`, which compares each active
node's stored `content_hash` against the live content on disk (local clone)
or via the GitHub API. Mutation commands (`node create`, `node update`)
are deferred; agents create nodes by writing files directly.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.core.freshness import check_all_nodes, check_node_freshness
from tripwire.core.node_store import load_node
from tripwire.core.store import ProjectNotFoundError, load_project
from tripwire.models.graph import FreshnessResult, FreshnessStatus

console = Console()


@click.group(name="node")
def node_cmd() -> None:
    """Concept node operations (check-only in v0)."""


@node_cmd.command("check")
@click.argument("node_id", required=False)
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
def node_check_cmd(node_id: str | None, project_dir: Path, output_format: str) -> None:
    """Check one node (if NODE_ID given) or every active node with a source.

    Fetches current content (local clone or GitHub API), hashes, and
    compares to the node's stored `source.content_hash`. Reports one of:
    `fresh`, `stale`, `source_missing`, `no_source`.
    """
    resolved = project_dir.expanduser().resolve()
    try:
        project = load_project(resolved)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if node_id is not None:
        try:
            node = load_node(resolved, node_id)
        except FileNotFoundError as exc:
            raise click.ClickException(str(exc)) from exc
        results = [check_node_freshness(node, project)]
    else:
        from tripwire.core.node_store import list_nodes

        results = check_all_nodes(list_nodes(resolved), project)

    if output_format == "json":
        click.echo(
            json.dumps(
                [asdict(r) for r in results],
                indent=2,
                default=str,
            )
        )
        return

    _render_table(results)


def _render_table(results: list[FreshnessResult]) -> None:
    if not results:
        console.print("[dim]no active nodes with a source to check[/dim]")
        return
    table = Table(title="Node freshness", show_header=True)
    table.add_column("node")
    table.add_column("status")
    table.add_column("detail")
    for r in results:
        style = _status_style(r.status)
        table.add_row(
            r.node_id,
            f"[{style}]{r.status.value}[/{style}]",
            (r.detail or "")[:80],
        )
    console.print(table)


def _status_style(status: FreshnessStatus) -> str:
    return {
        FreshnessStatus.FRESH: "green",
        FreshnessStatus.STALE: "yellow",
        FreshnessStatus.SOURCE_MISSING: "red",
        FreshnessStatus.NO_SOURCE: "dim",
    }.get(status, "white")
