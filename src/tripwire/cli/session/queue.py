"""``tripwire session queue`` — readiness check + transition to queued.

Validates that a session is ready to be queued (readiness punch list
must be clean), then transitions ``planned → queued`` via the workflow
executor. Optionally promotes every member issue still in ``planned``
to ``queued`` in one shot via ``--promote-issues``.

Single command — no subcommands. Queueing is the only operation that
lives under ``session queue``; launching a queued session is a separate,
PM-managed command (``tripwire session spawn <id>``). Tripwire does not
auto-launch — ``queued`` is a PM-curated state and every launch is an
explicit invocation.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.session_readiness import check_readiness


@session_cmd.command(name="queue")
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


__all__ = ["session_queue_cmd"]
