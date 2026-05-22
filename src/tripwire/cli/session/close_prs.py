"""``tripwire session close-prs`` — close any open PR across session worktrees."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("close-prs")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_close_prs_cmd(session_id: str, project_dir: Path) -> None:
    """Close any open PR across the session's recorded worktrees.

    Iterates ``session.runtime_state.worktrees`` and calls the
    canonical :func:`tripwire.core.session_abandon._close_pr_for_branch`
    helper for each. Skips merged PRs. Best-effort — per-worktree
    failures are reported but never abort the loop.
    """
    from tripwire.core.session_abandon import _close_pr_for_branch

    _, session = _resolve_and_load_session(project_dir, session_id)

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    closed: list[int] = []
    errors: list[str] = []
    for wt in session.runtime_state.worktrees:
        if not wt.branch:
            continue
        verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
        if verdict.closed_pr is not None and verdict.closed_pr > 0:
            closed.append(verdict.closed_pr)
        if verdict.error:
            errors.append(verdict.error)

    for pr in closed:
        click.echo(f"closed PR #{pr}")
    for err in errors:
        click.echo(f"warning: {err}", err=True)
    if not closed and not errors:
        click.echo(f"session {session_id}: no open PRs to close")
