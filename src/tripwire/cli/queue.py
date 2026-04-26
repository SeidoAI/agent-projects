"""``tripwire queue`` — quota-aware auto-launcher daemon (KUI-96 §E1).

Lifecycle mirrors ``tripwire watch``:

  ``tripwire queue start [--background] [--cap-usd N] [--tick-sleep S]``
      Launch the queue daemon. Foreground by default; ``--background``
      forks a detached subprocess and prints the pid.

  ``tripwire queue status``
      Report whether the daemon is running for this project, and its pid
      / cap configuration if so.

  ``tripwire queue stop``
      SIGTERM the running daemon. No-op when not running.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from tripwire.core.process_helpers import is_alive, send_sigterm
from tripwire.core.queue_runner import (
    QueueRunner,
    QueueRunnerConfig,
    is_queue_running,
    logfile_path,
    pidfile_path,
    remove_pidfile,
    write_pidfile,
)


def _project_dir_option():
    return click.option(
        "--project-dir",
        type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
    )


@click.group(name="queue")
def queue_cmd() -> None:
    """Quota-aware auto-launcher daemon (KUI-96 §E1)."""


@queue_cmd.command("start")
@click.option(
    "--background",
    is_flag=True,
    help="Fork a detached subprocess; survives the parent shell exit.",
)
@click.option(
    "--cap-usd",
    type=float,
    default=200.0,
    show_default=True,
    help="USD cap for recent telemetry; the daemon defers above this.",
)
@click.option(
    "--tick-sleep",
    type=float,
    default=60.0,
    show_default=True,
    help="Seconds between policy ticks.",
)
@click.option(
    "--max-ticks",
    type=int,
    default=None,
    help="Bounded run for tests / scripted callers; default loops forever.",
)
@_project_dir_option()
def queue_start_cmd(
    background: bool,
    cap_usd: float,
    tick_sleep: float,
    max_ticks: int | None,
    project_dir: Path,
) -> None:
    """Start the queue daemon."""
    project_dir = project_dir.expanduser().resolve()
    if is_queue_running(project_dir):
        existing_pid = pidfile_path(project_dir).read_text().strip()
        raise click.ClickException(
            f"queue daemon already running for this project (pid {existing_pid})"
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
                    "queue",
                    "start",
                    "--project-dir",
                    str(project_dir),
                    "--cap-usd",
                    str(cap_usd),
                    "--tick-sleep",
                    str(tick_sleep),
                ],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        finally:
            log_fh.close()
        click.echo(
            f"queue daemon started in background (pid {proc.pid}) — log at {log_path}"
        )
        return

    cfg = QueueRunnerConfig(
        cap_usd_per_window=cap_usd,
        tick_sleep_seconds=tick_sleep,
    )
    runner = QueueRunner(project_dir=project_dir, config=cfg)
    write_pidfile(project_dir, os.getpid())
    click.echo(
        f"queue daemon: project={project_dir} cap=${cap_usd:.2f} "
        f"tick_sleep={tick_sleep}s (Ctrl-C to stop)"
    )
    try:
        runner.run_forever(max_ticks=max_ticks)
    finally:
        remove_pidfile(project_dir)


@queue_cmd.command("status")
@_project_dir_option()
def queue_status_cmd(project_dir: Path) -> None:
    """Show daemon status for this project."""
    project_dir = project_dir.expanduser().resolve()
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        click.echo("queue daemon: not running (no pidfile)")
        return
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError):
        click.echo("queue daemon: pidfile present but unreadable")
        return
    if is_alive(pid):
        click.echo(
            f"queue daemon: running (pid {pid}) — log at {logfile_path(project_dir)}"
        )
    else:
        click.echo(
            f"queue daemon: not running (stale pidfile {pid_path}, last pid {pid})"
        )


@queue_cmd.command("stop")
@_project_dir_option()
def queue_stop_cmd(project_dir: Path) -> None:
    """Stop the running daemon."""
    project_dir = project_dir.expanduser().resolve()
    pid_path = pidfile_path(project_dir)
    if not pid_path.exists():
        click.echo("queue daemon: not running (no pidfile to stop)")
        return
    try:
        pid = int(pid_path.read_text().strip())
    except (ValueError, OSError) as exc:
        raise click.ClickException(f"unreadable pidfile {pid_path}: {exc}") from exc
    sent = send_sigterm(pid)
    if sent:
        click.echo(f"queue daemon: SIGTERM sent to pid {pid}")
    else:
        click.echo(f"queue daemon: pid {pid} not found (already exited?)")
        try:
            pid_path.unlink()
        except FileNotFoundError:
            pass


__all__ = ["queue_cmd"]
