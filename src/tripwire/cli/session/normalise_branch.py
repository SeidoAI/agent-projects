"""``tripwire session normalise-branch`` — reset squash-merged worktree branches."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.gh_helpers import GhError, get_merged_pr_for_branch


@session_cmd.command("normalise-branch")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_normalise_branch_cmd(session_id: str, project_dir: Path) -> None:
    """Reset squash-merged worktree branches to ``origin/main``.

    For each recorded worktree, asks ``gh`` whether the PR for the
    branch was merged. If merged AND the local branch still carries
    commits not present on ``origin/main`` (the canonical fingerprint
    of a squash-merge — the original commits stay behind on the
    feature branch), runs ``git reset --hard origin/main`` in the
    worktree. Idempotent: a worktree whose branch is already at
    ``origin/main`` is left alone; an unmerged PR is left alone.

    Skips worktrees whose path is missing on disk (e.g. already
    cleaned up by ``session complete``) and reports them as warnings.
    """
    _, session = _resolve_and_load_session(project_dir, session_id)

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    reset: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        if not wt_path.is_dir():
            skipped.append(f"{wt_path}: worktree missing")
            continue

        # Look up the PR for this branch — gh may return nothing if no
        # PR was ever opened; we treat that as "nothing to normalise".
        try:
            pr = get_merged_pr_for_branch(wt.branch, cwd=wt_path)
        except GhError as exc:
            errors.append(f"gh pr list failed for {wt.branch}: {exc}")
            continue

        if pr is None or not pr.get("mergedAt"):
            skipped.append(f"{wt.branch}: PR not merged")
            continue

        # Squash detection — does the local branch have commits absent
        # from origin/main? `git rev-list --count origin/main..HEAD`
        # answers that in one shot.
        try:
            ahead = subprocess.run(
                ["git", "-C", str(wt_path), "rev-list", "--count", "origin/main..HEAD"],
                check=False,
                capture_output=True,
                text=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"git rev-list failed for {wt_path}: {exc}")
            continue
        if ahead.returncode != 0:
            errors.append(
                f"git rev-list for {wt_path} exit={ahead.returncode}: "
                f"{(ahead.stderr or '').strip()}"
            )
            continue
        try:
            count = int((ahead.stdout or "0").strip())
        except ValueError:
            errors.append(f"git rev-list returned non-int for {wt_path}")
            continue
        if count == 0:
            skipped.append(f"{wt.branch}: already at origin/main")
            continue

        try:
            subprocess.run(
                ["git", "-C", str(wt_path), "reset", "--hard", "origin/main"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            errors.append(
                f"git reset --hard origin/main for {wt_path} failed: "
                f"{(exc.stderr or '').strip()}"
            )
            continue
        reset.append(wt.worktree_path)

    for path in reset:
        click.echo(f"reset to origin/main: {path}")
    for entry in skipped:
        click.echo(f"skipped: {entry}", err=True)
    for err in errors:
        click.echo(f"warning: {err}", err=True)
