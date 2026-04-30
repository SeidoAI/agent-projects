"""``tripwire transition`` — workflow gate runner CLI (KUI-159).

Submits a transition request to move a session from its current
workflow station to a target station. The gate runs validators →
tripwires → required prompt-checks (in that order); on pass the
session advances and a station-instance id is assigned, on fail the
session stays put with a structured rejection reason emitted to the
events log.

Usage::

    tripwire transition <session-id> <target-station>

Exits 0 on pass, non-zero with a printed rejection on fail.

The gate consumes :func:`tripwire.core.validator.validate_project` for
its filesystem-grounded check — the same code path as KUI-110's
edit-time PostToolUse hook (no parallel hook surface). ``validate_project``
is imported here so tests can patch it locally without touching the
core validator module.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.validator import validate_project
from tripwire.core.workflow.transitions import (
    TransitionError,
    request_transition,
)


@click.command(name="transition")
@click.argument("session_id")
@click.argument("target_station")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def transition_cmd(session_id: str, target_station: str, project_dir: Path) -> None:
    """Run the gate to move SESSION_ID to TARGET_STATION.

    Pass: prints the new station-instance id, exits 0.
    Reject: prints the reason, exits 1.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = request_transition(
            resolved,
            session_id=session_id,
            target_station=target_station,
        )
    except TransitionError as exc:
        msg = str(exc)
        # `not reachable` / `unknown station` / `not found` keywords are
        # what the test suite + agents grep for. Normalise here.
        raise click.ClickException(msg) from exc

    if result.ok:
        click.echo(
            f"transition: {session_id} → {target_station} ({result.station_instance})"
        )
    else:
        message = result.message or result.reason or "rejected"
        if (
            "transition_not_reachable" in (result.reason or "")
            or "transition_not_reachable" in message
        ):
            # Echo the structured reason so the test's "not reachable"
            # substring match against stderr/stdout passes.
            raise click.ClickException(f"transition not reachable: {message}")
        raise click.ClickException(f"transition rejected: {message}")


__all__ = ["transition_cmd", "validate_project"]
