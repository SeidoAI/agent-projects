"""``tripwire workspace list`` — enumerate registered projects."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import click

from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.workspace_store import load_workspace, workspace_exists


@dataclass
class ProjectListRow:
    slug: str
    name: str
    path: str
    path_exists: bool
    last_pulled_sha: str | None
    last_pulled_at: str | None


@workspace_cmd.command("list")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def workspace_list_cmd(workspace_dir: Path, output_format: str) -> None:
    """List registered projects with sync state."""
    resolved = workspace_dir.expanduser().resolve()
    if not workspace_exists(resolved):
        raise click.ClickException(f"no workspace.yaml at {resolved}")
    ws = load_workspace(resolved)

    rows = []
    for p in ws.projects:
        path_exists = (resolved / p.path).resolve().exists()
        rows.append(
            ProjectListRow(
                slug=p.slug,
                name=p.name,
                path=p.path,
                path_exists=path_exists,
                last_pulled_sha=p.last_pulled_sha,
                last_pulled_at=(
                    p.last_pulled_at.isoformat() if p.last_pulled_at else None
                ),
            )
        )

    if output_format == "json":
        click.echo(json.dumps([asdict(r) for r in rows], indent=2))
        return

    if not rows:
        click.echo("no projects registered")
        return
    for r in rows:
        mark = "✓" if r.path_exists else "✗"
        status = "" if r.path_exists else "  (path not found — orphan)"
        click.echo(f"  {mark} {r.slug:12s} {r.name:20s} {r.path}{status}")
    orphans = sum(1 for r in rows if not r.path_exists)
    if orphans:
        click.echo(f"\n{orphans} orphan — run `tripwire workspace prune --force`")
