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

from tripwire.core.freshness import (
    check_all_nodes,
    check_node_freshness,
    fetch_content,
    hash_content,
)
from tripwire.core.node_store import load_node, save_node
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
@click.option(
    "--update",
    is_flag=True,
    default=False,
    help=(
        "Refresh the node's source.content_hash to match current content. "
        "Requires NODE_ID. KUI-130 / A5."
    ),
)
@click.option(
    "--bump-contract",
    is_flag=True,
    default=False,
    help=(
        "When passed with --update, also increment version and set "
        "contract_changed_at to the new version. PM uses this to mark "
        "a contract-change bump that invalidates pinned consumers."
    ),
)
def node_check_cmd(
    node_id: str | None,
    project_dir: Path,
    output_format: str,
    update: bool,
    bump_contract: bool,
) -> None:
    """Check one node (if NODE_ID given) or every active node with a source.

    Fetches current content (local clone or GitHub API), hashes, and
    compares to the node's stored `source.content_hash`. Reports one of:
    `fresh`, `stale`, `source_missing`, `no_source`.

    With ``--update`` (requires NODE_ID), the command rewrites the
    node's stored ``content_hash`` to match current content. With
    ``--update --bump-contract``, also increments ``version`` and sets
    ``contract_changed_at`` to the new version, which makes any
    ``[[node-id@v(N-1)]]`` pin downstream stale.
    """
    if bump_contract and not update:
        raise click.ClickException(
            "--bump-contract requires --update; the bump only applies "
            "alongside a content_hash refresh."
        )
    if update and node_id is None:
        raise click.ClickException(
            "--update requires a NODE_ID. Refusing to rehash every node "
            "in the project at once."
        )

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
        if update:
            results = [_apply_update(resolved, node, project, bump_contract)]
        else:
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


def _apply_update(
    project_dir: Path,
    node,
    project,
    bump_contract: bool,
) -> FreshnessResult:
    """Refresh content_hash (and optionally bump version) for one node."""
    if node.source is None:
        raise click.ClickException(
            f"Node {node.id!r} has no source field; nothing to update."
        )
    content = fetch_content(node.source, project)
    if content is None:
        raise click.ClickException(
            f"Could not fetch source for node {node.id!r} "
            f"({node.source.repo}:{node.source.path}). "
            "Check the local clone path in project.yaml.repos or that "
            "`gh` is authenticated."
        )

    new_hash = hash_content(content)
    updates = {
        "source": node.source.model_copy(update={"content_hash": new_hash}),
    }
    if bump_contract:
        new_version = node.version + 1
        updates["version"] = new_version
        updates["contract_changed_at"] = new_version

    refreshed = node.model_copy(update=updates)
    save_node(project_dir, refreshed)

    return FreshnessResult(
        node_id=node.id,
        status=FreshnessStatus.FRESH,
        detail=(
            "updated content_hash"
            + (f"; version bumped to v{refreshed.version}" if bump_contract else "")
        ),
        current_hash=new_hash,
        stored_hash=new_hash,
    )


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
