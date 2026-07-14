"""``tripwire session logs`` — show log files for a session."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("logs")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--tail",
    "tail_lines",
    type=int,
    default=50,
    show_default=True,
    help="Number of lines to show from the tail of the latest log file.",
)
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Dump the entire latest log file instead of tailing.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    default=False,
    help="List all log files for the session; don't dump contents.",
)
def session_logs_cmd(
    session_id: str,
    project_dir: Path,
    tail_lines: int,
    full: bool,
    list_only: bool,
) -> None:
    """Show log files for a session.

    Per-spawn logs accumulate under the shared
    ``~/.tripwire/logs/<project-slug>/`` directory as
    ``<session_id>-<timestamp>.log``. This subcommand surfaces them
    without requiring operators to grep the filesystem by hand.
    """
    _, session = _resolve_and_load_session(project_dir, session_id)

    log_path_str = session.runtime_state.log_path
    if not log_path_str:
        raise click.ClickException(
            f"session '{session_id}' has no recorded log_path — "
            "the session may never have been spawned."
        )
    latest_log = Path(log_path_str).expanduser()
    log_dir = latest_log.parent
    if not log_dir.is_dir():
        raise click.ClickException(f"log directory does not exist: {log_dir}")

    matches = sorted(log_dir.glob(f"{session_id}-*.log"))
    if not matches and latest_log.is_file():
        matches = [latest_log]
    if not matches:
        raise click.ClickException(f"no log files found for session '{session_id}'")

    if list_only:
        for path in matches:
            st = path.stat()
            ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            click.echo(f"  {path.name}  {st.st_size:>10} bytes  {ts}")
        return

    latest = matches[-1]
    content = latest.read_text(encoding="utf-8", errors="replace")
    if full:
        click.echo(content, nl=False)
        return
    lines = content.splitlines()
    for line in lines[-tail_lines:]:
        click.echo(line)
