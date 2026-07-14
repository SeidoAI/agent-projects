"""``tripwire session pause`` — pause via runtime, transition to paused."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.process_helpers import is_alive


@session_cmd.command("pause")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_pause_cmd(session_id: str, project_dir: Path) -> None:
    """Pause the session via its runtime, transition to paused."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    resolved, session = _resolve_and_load_session(project_dir, session_id)

    if session.status != "executing":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'executing' to pause"
        )

    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime = get_runtime(spawn.invocation.runtime)

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    # For subprocess runtime, a dead pid means the agent already exited
    # (cleanly or otherwise). Surface that as 'failed' — pause doesn't
    # make sense once the process is gone.
    pid = session.runtime_state.pid
    if pid and not is_alive(pid):
        try:
            result = execute_transition(
                resolved,
                workflow_id="coding-session",
                instance_id=session_id,
                target_status="failed",
                flags={},
            )
        except TransitionError as exc:
            raise click.ClickException(str(exc)) from exc
        if not result.ok:
            raise click.ClickException(
                f"transition rejected: {result.message or result.reason}"
            )
        click.echo(f"Warning: PID {pid} not alive — session '{session_id}' → failed")
        return

    try:
        runtime.pause(session)
    except RuntimeError as exc:
        click.echo(f"Warning: {exc}", err=True)
        click.echo(
            f"Session '{session_id}' remains 'executing' — state matches reality"
        )
        return

    try:
        result = execute_transition(
            resolved,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="paused",
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc
    if not result.ok:
        raise click.ClickException(
            f"transition rejected: {result.message or result.reason}"
        )
    click.echo(f"Session '{session_id}' → paused")
