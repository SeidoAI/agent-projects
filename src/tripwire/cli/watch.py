"""``tripwire watch`` — post-PR auto-check daemon (v0.7.9 §A8).

Lifecycle:

  ``tripwire watch start [--background] [--poll-interval N]``
      Launch the daemon. Foreground by default; ``--background``
      forks a detached subprocess and prints the pid.

  ``tripwire watch status``
      Report whether the daemon is running for this project, and the
      pid if so.

  ``tripwire watch stop``
      SIGTERM the running daemon. No-op when not running.

  ``tripwire watch logs [--no-follow]``
      Tail the daemon's log file. ``--no-follow`` prints once and
      exits (used by tests + scripted callers).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import click

from tripwire.core.github_client import resolve_token
from tripwire.core.pr_watcher_daemon import (
    DaemonConfig,
    WatchDaemon,
    is_daemon_running,
    logfile_path,
    pidfile_path,
)
from tripwire.core.process_helpers import is_alive, send_sigterm


def _project_dir_option():
    return click.option(
        "--project-dir",
        type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
    )


@click.group(name="watch")
def watch_cmd() -> None:
    """Post-PR auto-check daemon (v0.7.9 §A8)."""


@watch_cmd.command("start")
@click.option(
    "--background",
    is_flag=True,
    help="Fork a detached subprocess; survives the parent shell exit.",
)
@click.option(
    "--poll-interval",
    type=float,
    default=300.0,
    show_default=True,
    help="Seconds between PR poll cycles.",
)
@_project_dir_option()
def watch_start_cmd(background: bool, poll_interval: float, project_dir: Path) -> None:
    """Start the watch daemon."""
    project_dir = project_dir.expanduser().resolve()
    if is_daemon_running(project_dir):
        existing_pid = pidfile_path(project_dir).read_text().strip()
        raise click.ClickException(
            f"watch daemon already running for this project (pid {existing_pid})"
        )
    if background:
        log_path = logfile_path(project_dir)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("a", encoding="utf-8")
        try:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "tripwire.cli.main",
                    "watch",
                    "start",
                    "--project-dir",
                    str(project_dir),
                    "--poll-interval",
                    str(poll_interval),
                ],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_fh.close()
        click.echo(
            f"watch daemon started in background (pid {proc.pid}) — log at {log_path}"
        )
        return
    cfg = DaemonConfig(
        project_dir=project_dir,
        poll_interval=poll_interval,
        token=resolve_token(),
    )
    daemon = WatchDaemon(cfg)
    click.echo(
        f"watch daemon: project={project_dir} poll_interval={poll_interval}s "
        "(Ctrl-C to stop)"
    )
    daemon.run_forever()


@watch_cmd.command("status")
@_project_dir_option()
def watch_status_cmd(project_dir: Path) -> None:
    """Show daemon status for this project."""
    project_dir = project_dir.expanduser().resolve()
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        click.echo("watch daemon: not running (no pidfile)")
        return
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        click.echo("watch daemon: pidfile present but unreadable")
        return
    if is_alive(pid):
        click.echo(
            f"watch daemon: running (pid {pid}) — log at {logfile_path(project_dir)}"
        )
    else:
        click.echo(
            f"watch daemon: not running (stale pidfile {pid_path}, last pid {pid})"
        )


@watch_cmd.command("stop")
@_project_dir_option()
def watch_stop_cmd(project_dir: Path) -> None:
    """Stop the running daemon."""
    project_dir = project_dir.expanduser().resolve()
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        click.echo("watch daemon: not running (no pidfile to stop)")
        return
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError) as exc:
        raise click.ClickException(f"unreadable pidfile {pid_path}: {exc}") from exc
    sent = send_sigterm(pid)
    if sent:
        click.echo(f"watch daemon: SIGTERM sent to pid {pid}")
    else:
        click.echo(f"watch daemon: pid {pid} not found (already exited?)")
        try:
            pid_path.unlink()
        except FileNotFoundError:
            pass


@watch_cmd.command("logs")
@click.option(
    "--no-follow", is_flag=True, help="Print once and exit instead of tailing."
)
@_project_dir_option()
def watch_logs_cmd(no_follow: bool, project_dir: Path) -> None:
    """Tail the daemon log."""
    project_dir = project_dir.expanduser().resolve()
    log = logfile_path(project_dir)
    if not log.exists():
        click.echo(f"watch daemon: no log file yet at {log}")
        return
    if no_follow:
        click.echo(log.read_text(encoding="utf-8"), nl=False)
        return
    # Tail mode: emit existing contents, then poll for new lines.
    with log.open("r", encoding="utf-8", errors="replace") as f:
        click.echo(f.read(), nl=False)
        try:
            while True:
                line = f.readline()
                if line:
                    click.echo(line, nl=False)
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            return


__all__ = ["watch_cmd"]
