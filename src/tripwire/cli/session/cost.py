"""``tripwire session cost`` — sum per-category token cost for a session."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import console


@session_cmd.command("cost")
@click.argument("session_id")
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
def session_cost_cmd(
    session_id: str,
    project_dir: Path,
    output_format: str,
) -> None:
    """Sum the per-token-category cost for a session's stream-json log.

    Pricing comes from ``data/anthropic_pricing.yaml`` (refresh
    manually). Sessions that have never spawned (no recorded
    ``runtime_state.log_path``) report a zero breakdown rather than
    erroring — useful for the ``Cost`` column in ``session list``.
    """
    from tripwire.core.session_cost import compute_session_cost

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        breakdown = compute_session_cost(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if output_format == "json":
        payload = {"session_id": session_id, **breakdown.as_dict()}
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title=f"Cost: {session_id}", show_header=True)
    table.add_column("category")
    table.add_column("tokens", justify="right")
    table.add_column("usd", justify="right")
    rows: list[tuple[str, int, float]] = [
        ("input", breakdown.input_tokens, breakdown.input_usd),
        ("output", breakdown.output_tokens, breakdown.output_usd),
        ("cache_read", breakdown.cache_read_tokens, breakdown.cache_read_usd),
        ("cache_write", breakdown.cache_write_tokens, breakdown.cache_write_usd),
    ]
    for label, tokens, usd in rows:
        table.add_row(label, f"{tokens:,}", f"${usd:.4f}")
    table.add_row("[bold]total[/bold]", "", f"[bold]${breakdown.total_usd:.4f}[/bold]")
    console.print(table)
    if breakdown.models_used:
        console.print(f"[dim]models seen: {', '.join(breakdown.models_used)}[/dim]")
