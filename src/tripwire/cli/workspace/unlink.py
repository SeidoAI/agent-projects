"""``tripwire workspace unlink`` — remove the project's workspace link."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.store import load_project as load_project_config
from tripwire.core.workspace_store import (
    load_workspace,
    remove_project,
    workspace_exists,
)


@workspace_cmd.command("unlink")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Remove the project-side pointer even if the workspace is missing.",
)
def workspace_unlink_cmd(project_dir: Path, force: bool) -> None:
    """Unlink this project from its workspace."""
    proj = project_dir.expanduser().resolve()
    _require_project(proj)

    from tripwire.core.store import save_project

    cfg = load_project_config(proj)
    if cfg.workspace is None:
        raise click.ClickException("project is not linked to any workspace")

    ws_resolved = (proj / cfg.workspace.path).resolve()

    if workspace_exists(ws_resolved):
        ws = load_workspace(ws_resolved)
        for p in list(ws.projects):
            if (ws_resolved / p.path).resolve() == proj:
                try:
                    remove_project(ws_resolved, slug=p.slug)
                except ValueError:
                    pass
    elif not force:
        raise click.ClickException(
            f"workspace at {ws_resolved} not found; re-run with --force "
            "to remove the project-side pointer only"
        )

    cfg_new = cfg.model_copy(update={"workspace": None})
    save_project(proj, cfg_new)
    click.echo("✓ Unlinked from workspace.")
