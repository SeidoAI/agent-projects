"""``tripwire workspace merge-resolve`` — finalize an agent-resolved merge."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.cli.workspace._helpers import _git_head, _resolve_workspace


@workspace_cmd.command("merge-resolve")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_merge_resolve_cmd(node_id: str, project_dir: Path) -> None:
    """Finalize an agent-resolved merge.

    Validates the resolved node against the schema, bumps its
    workspace_sha to the current workspace HEAD, and deletes the
    merge brief. If validation fails, the brief is preserved so the
    agent can fix the node and retry.
    """
    from tripwire.core.merge_brief import (
        delete_merge_brief,
        list_pending_briefs,
        load_merge_brief,
    )
    from tripwire.core.node_store import load_node, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    brief = load_merge_brief(proj, node_id)
    if brief is None:
        raise click.ClickException(
            f"no pending merge brief for '{node_id}' at "
            f".tripwire/merge-briefs/{node_id}.yaml"
        )

    try:
        node = load_node(proj, node_id)
    except Exception as exc:
        raise click.ClickException(
            f"node '{node_id}' failed to load after resolve: {exc}. "
            "Brief preserved — fix the node file and retry."
        ) from exc

    workspace_head = _git_head(ws_dir)
    resolved = node.model_copy(
        update={
            "origin": "workspace",
            "scope": "workspace",
            "workspace_sha": workspace_head,
            "workspace_pulled_at": datetime.now(tz=timezone.utc),
        }
    )
    save_node(proj, resolved, update_cache=False)
    delete_merge_brief(proj, node_id)

    click.echo(f"✓ {node_id}: resolved")
    click.echo(f"  workspace_sha → {workspace_head}")
    click.echo("  brief deleted")

    remaining = list_pending_briefs(proj)
    if remaining:
        click.echo(f"\n{len(remaining)} brief(s) still pending: {', '.join(remaining)}")
    else:
        click.echo("\nAll merges resolved. Pull complete.")
