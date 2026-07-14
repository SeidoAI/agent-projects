"""``tripwire workspace fork`` — detach a workspace-origin node from sync."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd


@workspace_cmd.command("fork")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_fork_cmd(node_id: str, project_dir: Path) -> None:
    """Detach a workspace-origin node from sync (scope workspace → local).

    The node keeps origin=workspace + workspace_sha for audit, but pull
    and push skip it. Useful when a project needs to specialize a node
    without tracking upstream changes.
    """
    from tripwire.core.node_store import load_node, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)

    try:
        node = load_node(proj, node_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"node '{node_id}' not found in project") from exc

    if node.origin != "workspace":
        raise click.ClickException(
            f"node '{node_id}' has origin=local — nothing to fork from"
        )
    if node.scope == "local":
        click.echo(
            f"node '{node_id}' is already forked (origin=workspace, scope=local)"
        )
        return

    forked = node.model_copy(update={"scope": "local"})
    save_node(proj, forked, update_cache=False)
    click.echo(
        f"✓ Forked {node_id}. origin={forked.origin} scope={forked.scope} "
        f"workspace_sha={forked.workspace_sha} (kept for audit)."
    )
