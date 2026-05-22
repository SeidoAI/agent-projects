"""``tripwire session attach`` — attach to a running session via its runtime."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("attach")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_attach_cmd(session_id: str, project_dir: Path) -> None:
    """Attach to a running session. Behaviour is runtime-specific:
    subprocess runtimes exec `tail -f <log>`; manual runtimes print
    the command to run."""
    import os

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    resolved, session = _resolve_and_load_session(project_dir, session_id)

    spawn = load_resolved_spawn_config(resolved, session=session)
    try:
        runtime = get_runtime(spawn.invocation.runtime)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    cmd = runtime.attach_command(session)
    if isinstance(cmd, AttachExec):
        os.execvp(cmd.argv[0], cmd.argv)
    elif isinstance(cmd, AttachInstruction):
        click.echo(cmd.message)
    else:
        raise click.ClickException(
            f"Runtime '{runtime.name}' returned unexpected attach command."
        )
