"""``tripwire session transition`` — generic workflow-executor transition."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd

# Session-status transitions are declared in `workflow.yaml` and
# executed by `tripwire.core.workflow.transitions.execute_transition`,
# which resolves the matching route, runs the gate (tripwires, JIT
# prompts, prompt-checks, artifact-existence), and atomically writes
# `session.status` plus a small fixed set of post-write housekeeping
# records (engagement close, audit, telemetry, ack reset).
#
# External side effects historically dispatched by the executor
# (sweep issues, rebase PT, kill runtime, flip draft PRs, etc.) now
# live as Layer-1/Layer-2 CLI wrappers and direct-mutation cli paths.


@session_cmd.command("transition")
@click.argument("session_id")
@click.argument("target_status")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_transition_cmd(
    session_id: str,
    target_status: str,
    project_dir: Path,
) -> None:
    """Transition a session's status via the workflow executor.

    Routes through ``tripwire.core.workflow.transitions.execute_transition``,
    which resolves the matching route in ``workflow.yaml`` from
    ``(current_status, target_status)``, runs the route's gate (tripwires
    listed in ``controls.tripwires``, JIT prompts, prompt-checks, consumed
    artifacts), atomically flips the status, then runs a small fixed set
    of best-effort post-write hooks (close active engagement on terminal
    transitions, append audit + telemetry records, reset acks if the
    route opts in).

    External side effects historically declared by ``route.side_effects``
    (sweep, PT-rebase, draft-PR flips, kill runtime, etc.) now live as
    Layer-1 CLI wrappers and direct-mutation cli paths; routes still
    document them informationally but the executor no longer orchestrates
    them. Per-route validation runs as the route's ``controls.tripwires``
    gate (the full project validator runs as ``tripwire validate``).
    """
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = execute_transition(
            resolved,
            session_id=session_id,
            target_status=target_status,
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.ok:
        raise click.ClickException(
            f"transition not reachable: {result.message or result.reason}"
        )

    click.echo(f"Session '{session_id}' → {target_status}")
