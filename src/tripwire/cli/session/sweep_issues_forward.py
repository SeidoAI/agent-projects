"""``tripwire session sweep-issues-forward`` — drive member issues to match session state."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("sweep-issues-forward")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_sweep_issues_forward_cmd(session_id: str, project_dir: Path) -> None:
    """Drive every member issue forward to match the session's current state.

    The target issue state is derived from the session's current status
    via :func:`tripwire.core.status_contract.sweep_target_for` (e.g. a
    ``verified`` session sweeps issues to ``verified``; ``completed``
    sweeps to ``completed``). Issues already at-or-beyond the target
    are no-ops; off-path issues (``deferred``, ``abandoned``) are left
    alone — same contract as the ``sweep_issues_forward`` side-effect.

    v0.13.2 (#6): previously this shelled out to
    ``tripwire transition issue-closure <key> <target>`` per issue, but
    ``execute_transition`` looks up an exact ``(from, to)`` route and
    the issue-closure workflow only declares single-step routes — so
    sweeping a ``planned`` issue to ``completed`` failed with
    ``transition_not_reachable``, and issues already at-target failed
    because there's no self-edge. Use the in-process sweep helper
    instead, which mirrors the original v0.12 behaviour (skip already-
    at-or-beyond, skip off-path, skip missing) the workflow doesn't yet
    express as a multi-step route.
    """
    from tripwire.core.status_contract import sweep_issues, sweep_target_for

    resolved, session = _resolve_and_load_session(project_dir, session_id)

    target = sweep_target_for(session.status.value)
    if target is None:
        click.echo(
            f"session {session_id}: status {session.status.value!r} has no sweep target"
        )
        return

    if not session.issues:
        click.echo(f"session {session_id}: no member issues; nothing to sweep")
        return

    sweep = sweep_issues(resolved, session, session.status.value)
    for key in sweep.changed:
        click.echo(f"advanced {key} → {target}")
    for p in sweep.partial:
        click.echo(
            f"PARTIAL {p.issue_key}: {p.started_at_status} → "
            f"{p.reached_status} (failed {p.failed_at_step}: {p.reason})",
            err=True,
        )
    click.echo(
        f"session {session_id}: swept {len(sweep.changed)} of "
        f"{len(session.issues)} issue(s) → {target}"
        + (f"; {len(sweep.partial)} stuck mid-lifecycle" if sweep.partial else "")
    )
