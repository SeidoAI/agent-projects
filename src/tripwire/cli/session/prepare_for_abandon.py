"""``tripwire session prepare-for-abandon`` — tear down session live state."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.git_helpers import worktree_remove


@session_cmd.command("prepare-for-abandon")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_prepare_for_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Tear down a session's live state before the abandon transition.

    Runs three Layer-1 wrappers back to back, each best-effort:

    1. ``kill-runtime`` — SIGTERM the recorded runtime pid (no-op if none).
    2. ``close-prs`` — close any open PRs on the session's worktrees.
    3. ``remove-worktrees`` — delete the worktree directories.

    Per-step failures are collected, not raised — we always make a best
    effort to complete every step. Exit 0 if everything succeeded or
    was a no-op; exit 1 with a per-step summary if any step had a hard
    failure so the operator knows what to clean up manually.
    """
    from tripwire.core.session_abandon import _close_pr_for_branch

    _, session = _resolve_and_load_session(project_dir, session_id)

    failures: list[str] = []

    # Step 1: kill-runtime — same logic as session_kill_runtime_cmd, inlined
    # so we can collect errors rather than re-raise.
    import os
    import signal

    pid = session.runtime_state.pid if session.runtime_state else None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            click.echo(f"sent SIGTERM to pid {pid}")
        except ProcessLookupError:
            click.echo(f"pid {pid} already dead; skipping", err=True)
        except OSError as exc:
            failures.append(f"kill-runtime: failed to signal pid {pid}: {exc}")
    else:
        click.echo(f"session {session_id}: no runtime pid recorded; skipping")

    # Step 2: close-prs — same as session_close_prs_cmd.
    if session.runtime_state and session.runtime_state.worktrees:
        closed: list[int] = []
        for wt in session.runtime_state.worktrees:
            if not wt.branch:
                continue
            try:
                verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
            except Exception as exc:  # pragma: no cover - defensive
                failures.append(f"close-prs: {wt.branch}: {exc}")
                continue
            if verdict.closed_pr is not None and verdict.closed_pr > 0:
                closed.append(verdict.closed_pr)
            if verdict.error:
                failures.append(f"close-prs: {verdict.error}")
        for pr in closed:
            click.echo(f"closed PR #{pr}")
        if not closed:
            click.echo(f"session {session_id}: no open PRs to close")
    else:
        click.echo(f"session {session_id}: no recorded worktrees for close-prs")

    # Step 3: remove-worktrees — same as session_remove_worktrees_cmd.
    if session.runtime_state and session.runtime_state.worktrees:
        removed: list[str] = []
        for wt in session.runtime_state.worktrees:
            try:
                worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
                removed.append(wt.worktree_path)
            except (subprocess.SubprocessError, OSError) as exc:
                failures.append(f"remove-worktrees: {wt.worktree_path}: {exc}")
        for wt_path in removed:
            click.echo(f"removed worktree: {wt_path}")
        if not removed and not any(f.startswith("remove-worktrees") for f in failures):
            click.echo(f"session {session_id}: no worktrees to remove")
    else:
        click.echo(f"session {session_id}: no recorded worktrees for remove-worktrees")

    if failures:
        click.echo(
            f"session {session_id}: {len(failures)} step(s) failed during prepare-for-abandon",
            err=True,
        )
        for f in failures:
            click.echo(f"  {f}", err=True)
        raise click.ClickException(
            f"prepare-for-abandon had hard failures for {session_id}"
        )

    click.echo(f"session {session_id}: ready for abandon")
