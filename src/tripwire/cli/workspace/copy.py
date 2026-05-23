"""``tripwire workspace copy`` — import workspace nodes into project."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.cli.workspace._helpers import (
    _git_head,
    _load_workspace_node,
    _resolve_workspace,
)


@workspace_cmd.command("copy")
@click.argument("node_ids", nargs=-1, required=True)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_copy_cmd(node_ids: tuple[str, ...], project_dir: Path) -> None:
    """Import workspace nodes into this project for the first time.

    Each node is stamped with origin=workspace, scope=workspace, and
    workspace_sha = current workspace HEAD. Refuses when the node id
    already exists locally — use `pull` (to refresh) or `fork` (to
    detach) instead.
    """
    from tripwire.core.node_store import node_exists, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    head_sha = _git_head(ws_dir)
    copied: list[str] = []
    skipped: list[tuple[str, str]] = []

    for node_id in node_ids:
        if node_exists(proj, node_id):
            skipped.append((node_id, "already exists locally"))
            continue
        try:
            canonical = _load_workspace_node(ws_dir, node_id)
        except FileNotFoundError:
            skipped.append((node_id, "not found in workspace"))
            continue

        local_copy = canonical.model_copy(
            update={
                "origin": "workspace",
                "scope": "workspace",
                "workspace_sha": head_sha,
                "workspace_pulled_at": datetime.now(tz=timezone.utc),
            }
        )
        save_node(proj, local_copy, update_cache=False)
        copied.append(node_id)

    for node_id in copied:
        click.echo(f"✓ {node_id}")
    for node_id, reason in skipped:
        click.echo(f"✗ {node_id}: {reason}")
    click.echo(
        f"\n{len(copied)} of {len(node_ids)} node(s) copied; workspace_sha={head_sha}."
    )
    if skipped and not copied:
        raise click.exceptions.Exit(1)
