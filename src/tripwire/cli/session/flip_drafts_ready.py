"""``tripwire session flip-drafts-ready`` — flip drafts to ready-for-review."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("flip-drafts-ready")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_flip_drafts_ready_cmd(session_id: str, project_dir: Path) -> None:
    """Flip every draft PR on the session's worktrees to ready-for-review.

    Delegates to the canonical
    :func:`tripwire.core.session_complete._flip_drafts_to_ready` helper
    so the CLI surface stays in sync with the close-out path.
    """
    from tripwire.core.session_complete import _flip_drafts_to_ready

    _, session = _resolve_and_load_session(project_dir, session_id)

    _flip_drafts_to_ready(session)
    click.echo(f"flipped drafts to ready for session {session_id}")
