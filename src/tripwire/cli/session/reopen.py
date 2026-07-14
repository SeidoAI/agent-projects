"""``tripwire session reopen`` — move a completed session back to paused."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.gh_helpers import GhError, gh_pr_ready


@session_cmd.command("reopen")
@click.argument("session_id")
@click.option(
    "--reason",
    required=True,
    help="Why are you reopening? Recorded in the audit log.",
)
@click.option(
    "--reset-acks",
    "reset_acks",
    is_flag=True,
    default=False,
    help=(
        "Delete `.tripwire/acks/*-<session_id>-*.json` so the agent "
        "re-encounters every tripwire on resume. Use after substantial "
        "rework (PR closed + reopened, plan.md materially edited)."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_reopen_cmd(
    session_id: str, reason: str, reset_acks: bool, project_dir: Path
) -> None:
    """Move a completed session back to ``paused`` for PR-fix iteration.

    Thin wrapper — see :func:`tripwire.core.session_reopen.reopen_session`
    for the side-effect contract. The ready→draft PR flip is a separate
    Layer-1 command (``tripwire session flip-drafts-draft``); we invoke
    it in-process here before calling the lifecycle helper so the
    end-to-end CLI behaviour is single-command.
    """
    from tripwire.core.session_reopen import reopen_session

    # In-process prep: flip recorded draft PRs ready → draft. The daemon
    # paths skip this; the CLI wrapper does it so a single command does
    # the user-visible work.
    resolved, session_for_prep = _resolve_and_load_session(project_dir, session_id)
    flipped: list[str] = []
    for wt in session_for_prep.runtime_state.worktrees:
        if not wt.draft_pr_url:
            continue
        # Best-effort: a PR that's already draft, merged, or whose gh
        # session has expired returns non-zero. We don't block reopen
        # on the flip — swallow ``GhError`` (which now covers the
        # previous ``SubprocessError`` / ``OSError`` / ``FileNotFoundError``
        # surface uniformly).
        try:
            gh_pr_ready(wt.draft_pr_url, undo=True, cwd=wt.worktree_path)
            flipped.append(wt.draft_pr_url)
        except GhError:
            pass

    try:
        result = reopen_session(resolved, session_id, reason, reset_acks=reset_acks)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Stamp the in-process flip outcomes onto the result for the CLI
    # summary (the helper no longer owns the gh ready-undo step).
    result.draft_prs_flipped = flipped

    click.echo(f"Session '{session_id}' reopened (→ paused). Reason: {reason}")
    if reset_acks:
        click.echo(f"Reset {result.acks_reset_count} tripwire ack(s).")
    click.echo(f"Spawn the resumed agent: tripwire session spawn {session_id} --resume")
