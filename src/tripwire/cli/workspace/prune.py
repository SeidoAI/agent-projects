"""``tripwire workspace prune`` — remove orphan project entries."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.workspace_store import (
    load_workspace,
    remove_project,
    workspace_exists,
)


@workspace_cmd.command("prune")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Actually remove orphan entries. Default is dry-run.",
)
def workspace_prune_cmd(workspace_dir: Path, force: bool) -> None:
    """Remove orphan project entries (path no longer exists)."""
    resolved = workspace_dir.expanduser().resolve()
    if not workspace_exists(resolved):
        raise click.ClickException(f"no workspace.yaml at {resolved}")
    ws = load_workspace(resolved)
    orphans = [p for p in ws.projects if not (resolved / p.path).resolve().exists()]
    if not orphans:
        click.echo("no orphans")
        return
    if not force:
        click.echo("would remove:")
        for p in orphans:
            click.echo(f"  {p.slug} ({p.path})")
        click.echo("re-run with --force to actually remove")
        return
    for p in orphans:
        remove_project(resolved, slug=p.slug)
    click.echo(f"removed {len(orphans)} orphan(s)")
