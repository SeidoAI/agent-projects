"""``tripwire session analyze-routing`` — aggregate routing telemetry rows."""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import console


@session_cmd.command("analyze-routing")
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
def session_analyze_routing_cmd(project_dir: Path, output_format: str) -> None:
    """Aggregate ``.routing_telemetry.jsonl`` rows by route.

    Thin wrapper — see :func:`tripwire.core.routing_analysis.aggregate_routes`
    for the per-route metrics computed.
    """
    from tripwire.core.routing_analysis import aggregate_routes, render_routing_table
    from tripwire.core.routing_telemetry import read_telemetry

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = read_telemetry(resolved)
    routes_payload = aggregate_routes(rows)

    if output_format == "json":
        click.echo(
            json.dumps(
                {"total_sessions": len(rows), "routes": routes_payload}, indent=2
            )
        )
        return

    render_routing_table(routes_payload, console)
