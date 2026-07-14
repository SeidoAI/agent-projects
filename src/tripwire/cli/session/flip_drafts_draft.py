"""``tripwire session flip-drafts-draft`` — flip ready PRs back to draft."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.gh_helpers import GhError, gh_pr_ready


@session_cmd.command("flip-drafts-draft")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_flip_drafts_draft_cmd(session_id: str, project_dir: Path) -> None:
    """Flip every ready PR on the session's worktrees back to draft.

    Mirrors the ``flip_drafts_to_draft`` side-effect: for each worktree
    with a recorded ``draft_pr_url``, run ``gh pr ready <url> --undo``.
    Best-effort — ``gh`` errors are swallowed (the operator can re-run
    or inspect ``gh`` output directly).
    """
    _, session = _resolve_and_load_session(project_dir, session_id)

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    flipped: list[str] = []
    for wt in session.runtime_state.worktrees:
        if not wt.draft_pr_url:
            continue
        # Best-effort by contract: a PR that's already draft or merged
        # exits non-zero from gh, but the wrapper shouldn't fail loud —
        # the operator can re-run or inspect gh directly. Swallow
        # ``GhError`` here.
        try:
            gh_pr_ready(wt.draft_pr_url, undo=True)
            flipped.append(wt.draft_pr_url)
        except GhError:
            continue

    for url in flipped:
        click.echo(f"flipped to draft: {url}")
    if not flipped:
        click.echo(f"session {session_id}: no draft URLs to flip")
