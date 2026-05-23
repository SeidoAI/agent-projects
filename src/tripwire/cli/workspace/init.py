"""``tripwire workspace init`` — bootstrap a new workspace."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import click

from tripwire import __version__ as TRIPWIRE_VERSION
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.paths import workspace_nodes_dir
from tripwire.core.workspace_store import save_workspace, workspace_exists
from tripwire.models.workspace import Workspace


@workspace_cmd.command("init")
@click.option("--name", required=True, help="Human-readable workspace name.")
@click.option("--slug", required=True, help="Short alias (e.g. 'seido').")
@click.option("--description", default="", help="One-liner describing the workspace.")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_init_cmd(
    name: str, slug: str, description: str, workspace_dir: Path
) -> None:
    """Bootstrap a new workspace at WORKSPACE_DIR.

    Creates workspace.yaml, an empty nodes/ directory, and runs `git init`
    if the directory isn't already a git repo.
    """
    resolved = workspace_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if workspace_exists(resolved):
        raise click.ClickException(
            f"workspace already exists at {resolved} (workspace.yaml present)"
        )

    now = datetime.now(tz=timezone.utc)
    ws = Workspace(
        uuid=uuid4(),
        name=name,
        slug=slug,
        description=description,
        schema_version=1,
        tripwire_version=TRIPWIRE_VERSION,
        created_at=now,
        updated_at=now,
    )
    save_workspace(resolved, ws)
    workspace_nodes_dir(resolved).mkdir(parents=True, exist_ok=True)

    if not (resolved / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=resolved, check=True)

    click.echo(f"✓ Workspace '{name}' initialized at {resolved}")
    click.echo("  Next: from a project, `tripwire workspace link <path-to-workspace>`")
