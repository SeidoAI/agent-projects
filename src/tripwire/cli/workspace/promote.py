"""``tripwire workspace promote`` — flip local node scope=workspace + push."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.cli.workspace._helpers import _resolve_workspace
from tripwire.cli.workspace.push import workspace_push_cmd


@workspace_cmd.command("promote")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.pass_context
def workspace_promote_cmd(ctx: click.Context, node_id: str, project_dir: Path) -> None:
    """Promote a local node to workspace (scope local → workspace + push).

    Shortcut that flips ``scope`` and delegates to push. Refuses if the
    node is already workspace-origin (use pull/push directly) or if the
    workspace already has a node with the same id.
    """
    from tripwire.core.node_store import load_node, save_node
    from tripwire.core.paths import workspace_node_path

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    try:
        node = load_node(proj, node_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"node '{node_id}' not found in project") from exc

    if node.origin != "local":
        raise click.ClickException(
            f"node '{node_id}' is already origin=workspace; promote only "
            "applies to local-origin nodes. Use `tripwire workspace push` to "
            "send pending changes upstream."
        )

    if workspace_node_path(ws_dir, node_id).exists():
        raise click.ClickException(
            f"workspace already has a node with id '{node_id}'. Rename your "
            "local node, or pull + fork if you're intentionally overriding."
        )

    # Flip scope and delegate to push.
    promoted = node.model_copy(update={"scope": "workspace"})
    save_node(proj, promoted, update_cache=False)
    click.echo(f"marked {node_id} as scope=workspace; pushing...")
    ctx.invoke(
        workspace_push_cmd,
        project_dir=proj,
        nodes=node_id,
        dry_run=False,
    )
