"""``tripwire workspace link`` — register a project with a workspace."""

from __future__ import annotations

import os
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.store import load_project as load_project_config
from tripwire.core.workspace_store import (
    add_project,
    load_workspace,
    workspace_exists,
)
from tripwire.models.workspace import WorkspaceProjectEntry


@workspace_cmd.command("link")
@click.argument(
    "workspace_path",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--slug", required=True, help="Workspace-local alias for this project.")
def workspace_link_cmd(workspace_path: Path, project_dir: Path, slug: str) -> None:
    """Register the current project with a workspace (bidirectional)."""
    proj_resolved = project_dir.expanduser().resolve()
    ws_resolved = workspace_path.expanduser().resolve()
    _require_project(proj_resolved)

    if not workspace_exists(ws_resolved):
        raise click.ClickException(f"no workspace.yaml at {ws_resolved}")

    cfg = load_project_config(proj_resolved)
    if cfg.workspace is not None:
        raise click.ClickException(
            f"project is already linked to workspace at "
            f"{cfg.workspace.path}; run `tripwire workspace unlink` first"
        )

    # Write relative paths from each side.
    try:
        pointer_path = os.path.relpath(ws_resolved, proj_resolved)
    except ValueError:
        pointer_path = str(ws_resolved)
    try:
        ws_relative_back = os.path.relpath(proj_resolved, ws_resolved)
    except ValueError:
        ws_relative_back = str(proj_resolved)

    from tripwire.core.store import save_project
    from tripwire.models.project import ProjectWorkspacePointer

    # Write workspace-side FIRST. If it fails (e.g. duplicate slug,
    # lock timeout, write error) the project-side pointer hasn't been
    # touched yet — no one-sided link to clean up.
    add_project(
        ws_resolved,
        WorkspaceProjectEntry(slug=slug, name=cfg.name, path=ws_relative_back),
    )

    # Project-side: write workspace pointer. If THIS fails (unlikely —
    # it's a local file write), we have a workspace entry without a
    # project pointer, which is the safer half-state: `workspace list`
    # will show it and `workspace prune` can clean it up.
    cfg_new = cfg.model_copy(
        update={"workspace": ProjectWorkspacePointer(path=pointer_path)}
    )
    save_project(proj_resolved, cfg_new)

    ws = load_workspace(ws_resolved)
    click.echo(f"✓ Linked {cfg.name} ↔ workspace {ws.slug}")
    click.echo(f"  project.yaml.workspace.path: {pointer_path}")
    click.echo(f"  workspace.yaml.projects[{slug}].path: {ws_relative_back}")
