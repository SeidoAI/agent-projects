"""``tripwire session kill-runtime`` — SIGTERM the recorded runtime pid.

Layer-1 wrapper around the ``kill_runtime`` side-effect handler body.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("kill-runtime")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_kill_runtime_cmd(session_id: str, project_dir: Path) -> None:
    """SIGTERM the session's recorded runtime pid. Best-effort.

    Reads ``session.runtime_state.pid`` and sends ``SIGTERM``. A
    missing pid is a clean no-op; ``ESRCH`` (pid already dead) is
    swallowed; any other OS error surfaces as a click error so the
    operator can investigate.
    """
    import os
    import signal

    _, session = _resolve_and_load_session(project_dir, session_id)

    pid = session.runtime_state.pid if session.runtime_state else None
    if not pid:
        click.echo(
            f"session {session_id}: no runtime pid recorded; skipping",
            err=True,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"sent SIGTERM to pid {pid} (session {session_id})")
    except ProcessLookupError:
        click.echo(f"pid {pid} already dead; skipping", err=True)
    except OSError as exc:
        raise click.ClickException(f"failed to signal pid {pid}: {exc}") from exc
