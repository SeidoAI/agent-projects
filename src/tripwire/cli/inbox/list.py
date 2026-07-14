"""``tripwire inbox list`` — enumerate inbox entries."""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli.inbox._group import inbox_cmd
from tripwire.ui.services.inbox_service import list_inbox


@inbox_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--bucket",
    type=click.Choice(["blocked", "fyi"]),
    default=None,
    help="Filter by bucket.",
)
@click.option(
    "--resolved/--unresolved",
    "resolved",
    default=None,
    help="Filter by resolved state. Omit to show both.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["text", "json"]),
    default="text",
)
def inbox_list_cmd(
    project_dir: Path,
    bucket: str | None,
    resolved: bool | None,
    fmt: str,
) -> None:
    """List inbox entries."""
    project = project_dir.expanduser().resolve()
    items = list_inbox(project, bucket=bucket, resolved=resolved)
    if fmt == "json":
        click.echo(
            json.dumps(
                [
                    {
                        "id": i.id,
                        "bucket": i.bucket,
                        "title": i.title,
                        "author": i.author,
                        "created_at": i.created_at.isoformat(),
                        "resolved": i.resolved,
                    }
                    for i in items
                ],
                indent=2,
            )
        )
        return
    if not items:
        click.echo("(no inbox entries)")
        return
    for item in items:
        marker = "✓" if item.resolved else ("!" if item.bucket == "blocked" else "·")
        click.echo(f"{marker} [{item.bucket:7s}] {item.id}  {item.title}")
