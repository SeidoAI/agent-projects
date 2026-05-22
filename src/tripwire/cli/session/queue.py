"""``tripwire session queue`` — readiness + daemon under one namespace.

Combines two related operations under the ``session queue`` umbrella:

  ``tripwire session queue add <session-id>``
      Validate readiness and transition the session to ``queued``.
      Includes the ``--promote-issues`` flag that flips every session
      issue at ``planned`` to ``queued`` in one shot. This is the v0.14.0
      successor to the bare ``tripwire session queue <session-id>``
      surface that existed up through v0.13.x — the rename is forced by
      the introduction of the daemon subcommands (``start``, ``status``,
      ``stop``) under the same group.

  ``tripwire session queue start [--background] [--cap-usd N] [--tick-sleep S]``
      Launch the queue daemon. Foreground by default; ``--background``
      forks a detached subprocess and prints the pid.

  ``tripwire session queue status``
      Report whether the daemon is running for this project, and its pid
      / cap configuration if so.

  ``tripwire session queue stop``
      SIGTERM the running daemon. No-op when not running.

``session queue add`` collapses what used to be ``tripwire session
queue <id>`` (transition) — a Click group cannot host both a positional
argument and named subcommands. ``session queue start/...`` is the
v0.14.0 nesting of the former top-level ``tripwire queue`` daemon.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
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
from tripwire.core.session_readiness import check_readiness


def _project_dir_option():
    return click.option(
        "--project-dir",
        type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
        default=".",
        show_default=True,
    )


@session_cmd.group(name="queue")
def queue_cmd() -> None:
    """Queue operations: add to queue, run daemon."""


# ============================================================================
# ``session queue add <id>`` — readiness check + transition
# ============================================================================


@queue_cmd.command("add")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--promote-issues",
    "promote_issues",
    is_flag=True,
    default=False,
    help=(
        "Before queueing, flip every session issue currently in "
        "`planned` status to `queued`. Leaves other statuses alone."
    ),
)
def session_queue_cmd(session_id: str, project_dir: Path, promote_issues: bool) -> None:
    """Validate readiness and transition session to queued."""
    resolved, session = _resolve_and_load_session(project_dir, session_id)

    if session.status != "planned":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'planned' to queue"
        )

    if promote_issues:
        from tripwire.core.store import load_issue
        from tripwire.core.workflow.transitions import (
            TransitionError,
            execute_transition,
        )

        promoted = 0
        for issue_key in session.issues:
            try:
                issue = load_issue(resolved, issue_key)
            except FileNotFoundError:
                click.echo(f"  ! issue {issue_key} not found — skipping")
                continue
            if str(issue.status) != "planned":
                continue
            # Route through the executor — `execute_transition` is the
            # sole writer of every workflow instance's status. The
            # pre-v0.13.2 inline `issue.status = "queued"; save_issue(...)`
            # bypassed the issue-closure workflow's route checks.
            try:
                result = execute_transition(
                    resolved,
                    workflow_id="issue-closure",
                    instance_id=issue_key,
                    target_status="queued",
                )
            except TransitionError as exc:
                click.echo(f"  ! {issue_key}: {exc}")
                continue
            if not result.ok:
                click.echo(f"  ! {issue_key}: {result.message or result.reason}")
                continue
            click.echo(f"  {issue_key}: planned → queued")
            promoted += 1
        if promoted == 0:
            click.echo("  (no issues at 'planned' to promote)")

    report = check_readiness(resolved, session_id, kind="queue")
    if not report.ready:
        for item in report.items:
            if not item.passing:
                click.echo(f"  ✗ {item.label}")
                if item.fix_hint:
                    click.echo(f"    → {item.fix_hint}")
        raise click.ClickException("Not ready to queue — fix errors above")

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    try:
        result = execute_transition(
            resolved,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="queued",
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc
    if not result.ok:
        raise click.ClickException(
            f"transition rejected: {result.message or result.reason}"
        )
    click.echo(f"Session '{session_id}' → queued")


# ============================================================================
# Daemon subcommands (formerly ``tripwire queue start/status/stop``)
# ============================================================================


@queue_cmd.command("start")
@click.option(
    "--background",
    is_flag=True,
    help="Fork a detached subprocess; survives the parent shell exit.",
)
@click.option(
    "--cap-usd",
    type=float,
    default=None,
    help=(
        "USD cap for recent telemetry; the daemon defers above this. "
        "Defaults to `queue.cap_usd_per_window` from "
        "templates/runtime/defaults.yaml (project-overridable)."
    ),
)
@click.option(
    "--tick-sleep",
    type=float,
    default=None,
    help=(
        "Seconds between policy ticks. Defaults to "
        "`queue.tick_sleep_seconds` from templates/runtime/defaults.yaml "
        "(project-overridable)."
    ),
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
    cap_usd: float | None,
    tick_sleep: float | None,
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

    # Resolve runtime YAML defaults; click options (when provided)
    # override the YAML values. None → use the YAML floor.
    overrides: dict[str, float | int] = {}
    if cap_usd is not None:
        overrides["cap_usd_per_window"] = cap_usd
    if tick_sleep is not None:
        overrides["tick_sleep_seconds"] = tick_sleep
    cfg = QueueRunnerConfig.from_runtime(project_dir, **overrides)

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
                    "session",
                    "queue",
                    "start",
                    "--project-dir",
                    str(project_dir),
                    "--cap-usd",
                    str(cfg.cap_usd_per_window),
                    "--tick-sleep",
                    str(cfg.tick_sleep_seconds),
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

    runner = QueueRunner(project_dir=project_dir, config=cfg)
    write_pidfile(project_dir, os.getpid())
    click.echo(
        f"queue daemon: project={project_dir} cap=${cfg.cap_usd_per_window:.2f} "
        f"tick_sleep={cfg.tick_sleep_seconds}s (Ctrl-C to stop)"
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


__all__ = ["queue_cmd", "session_queue_cmd"]
