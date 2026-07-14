"""``tripwire session monitor`` — one-shot runtime snapshot."""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_store import list_sessions


@session_cmd.command("monitor")
@click.argument("session_ids", nargs=-1)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def session_monitor_cmd(
    session_ids: tuple[str, ...], project_dir: Path, output_format: str
) -> None:
    """One-shot runtime snapshot. With no args, monitors all executing sessions.

    The PM's `/pm-session-monitor` slash command wraps this in a self-paced
    loop via ScheduleWakeup.
    """
    from dataclasses import asdict

    from tripwire.core.session_monitor import take_snapshot

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    if session_ids:
        sessions = [s for s in sessions if s.id in session_ids]
    else:
        sessions = [s for s in sessions if s.status == "executing"]

    if not sessions:
        click.echo("No executing sessions.")
        return

    snaps = [take_snapshot(resolved, s.id) for s in sessions]

    if output_format == "json":
        click.echo(json.dumps([asdict(s) for s in snaps], indent=2, default=str))
        return

    for snap in snaps:
        click.echo(f"{snap.session_id}  {snap.status}  source={snap.source}")
        if snap.turn is not None:
            click.echo(f"  turn: {snap.turn}")
        if snap.total_cost_usd is not None:
            click.echo(f"  cost: ${snap.total_cost_usd:.2f}")
        if snap.latest_tool:
            click.echo(f"  latest tool: {snap.latest_tool}")
        if snap.branch:
            pr = f" (PR #{snap.pr_number})" if snap.pr_number else ""
            click.echo(f"  branch: {snap.branch}{pr}")
        if snap.errors:
            for err in snap.errors[-3:]:
                click.echo(f"  error: {err}")
        if snap.stuck:
            click.echo("  ⚑ STUCK (no log activity in 10min)")
        if snap.process_alive is False:
            click.echo("  ⚑ PROCESS DEAD")
        click.echo()
