"""``tripwire session list`` — enumerate every session with status + counts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import SessionSummary, console
from tripwire.core.session_store import list_sessions


@session_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def session_list_cmd(project_dir: Path, output_format: str) -> None:
    """List every session in the project."""
    from tripwire.core.session_cost import compute_cost_from_log

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    summaries: list[SessionSummary] = []
    for s in sessions:
        # KUI-96 §E2 — cost column. Walk the persisted log if any; a
        # session that never spawned has no log_path → zero cost.
        log_path_str = s.runtime_state.log_path
        cost = 0.0
        if log_path_str:
            cost = compute_cost_from_log(Path(log_path_str).expanduser()).total_usd
        summaries.append(
            SessionSummary(
                id=s.id,
                name=s.name,
                agent=s.agent,
                status=s.status,
                issue_count=len(s.issues),
                repo_count=len(s.repos),
                cost_usd=cost,
                over_budget=s.runtime_state.cost_overrun_at is not None,
            )
        )

    if output_format == "json":
        click.echo(json.dumps([asdict(s) for s in summaries], indent=2))
        return

    if not summaries:
        console.print("[dim]no sessions yet[/dim]")
        return

    table = Table(title="Sessions", show_header=True)
    table.add_column("id")
    table.add_column("name")
    table.add_column("agent")
    table.add_column("status")
    table.add_column("issues", justify="right")
    table.add_column("repos", justify="right")
    table.add_column("cost", justify="right")
    for s in summaries:
        # v0.7.10 §3.A4 — flag budget-driven pauses next to status so a
        # human reading `session list` can tell apart manual pauses
        # from monitor-driven cost-overrun pauses.
        status_cell = f"{s.status} (over budget)" if s.over_budget else s.status
        table.add_row(
            s.id,
            s.name,
            s.agent,
            status_cell,
            str(s.issue_count),
            str(s.repo_count),
            f"${s.cost_usd:.4f}" if s.cost_usd else "—",
        )
    console.print(table)
