"""``tripwire session abandon`` — kill runtime, close PRs, remove worktrees."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd


@session_cmd.command("abandon")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Abandon a session: kill runtime, close open PRs, remove worktrees,
    transition to `abandoned`.

    `abandoned` is the terminal-but-not-claimed-success path (v0.7.9
    §A4). Use it for sessions that can't legitimately reach `completed`.
    Issues are NOT closed as `completed` — they stay where they are; move
    them back to `planned` or to `abandoned` separately if appropriate.
    """
    from tripwire.core.session_abandon import (
        AbandonError,
        abandon_session,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = abandon_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc
    except AbandonError as exc:
        raise click.ClickException(str(exc)) from exc

    # All transition / runtime / PR / worktree work is in
    # core.session_abandon.abandon_session — including closing any open
    # PRs (both regular and draft) by branch, which subsumes v0.7.5's
    # `wt.draft_pr_url`-based close path.
    click.echo(f"Session '{session_id}' → abandoned")
    if result.runtime_killed:
        click.echo("  killed runtime handle")
    for pr in result.prs_closed:
        click.echo(f"  closed PR #{pr}")
    for pr in result.prs_skipped_merged:
        click.echo(f"  skipped merged PR #{pr}")
    for wt in result.worktrees_removed:
        click.echo(f"  removed worktree: {wt}")
    for err in result.errors:
        click.echo(f"  warning: {err}", err=True)
