"""``tripwire events`` — read-only inspection of the workflow events log.

Subcommands:

- ``tail`` — show the most recent N events (default 20).
- ``filter`` — narrow by workflow, instance, station, and/or event kind.

Both emit one JSON object per line (matches the on-disk format), so
output pipes cleanly into ``jq`` and other line-oriented tooling.

The events log is append-only and read-only via the CLI; emission
goes through :func:`tripwire.core.events.log.emit_event` from
validators, tripwires, and the transition runtime.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.events.log import read_events


@click.group(name="events")
def events_cmd() -> None:
    """Workflow events log (KUI-123) — read-only inspection."""


@events_cmd.command("tail")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--limit",
    type=int,
    default=20,
    show_default=True,
    help="Show this many of the most recent events.",
)
def events_tail_cmd(project_dir: Path, limit: int) -> None:
    """Show the last N events in chronological order, JSON-Lines."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = list(read_events(resolved))
    for row in rows[-limit:]:
        click.echo(json.dumps(row, ensure_ascii=False))


@events_cmd.command("filter")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--workflow", "workflow", default=None)
@click.option("--instance", "instance", default=None)
@click.option("--station", "station", default=None)
@click.option("--event", "event", default=None)
@click.option(
    "--limit",
    type=int,
    default=0,
    show_default=True,
    help="Show only the last N matches (0 = all).",
)
def events_filter_cmd(
    project_dir: Path,
    workflow: str | None,
    instance: str | None,
    station: str | None,
    event: str | None,
    limit: int,
) -> None:
    """Filter events by workflow / instance / station / event kind.

    Each filter narrows the result set; omitted filters are wildcards.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = list(
        read_events(
            resolved,
            workflow=workflow,
            instance=instance,
            station=station,
            event=event,
        )
    )
    if limit > 0:
        rows = rows[-limit:]
    for row in rows:
        click.echo(json.dumps(row, ensure_ascii=False))


__all__ = ["events_cmd"]
