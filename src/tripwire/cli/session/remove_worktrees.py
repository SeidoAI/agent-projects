"""``tripwire session remove-worktrees`` — delete recorded worktree dirs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session
from tripwire.core.git_helpers import worktree_remove


@session_cmd.command("remove-worktrees")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_remove_worktrees_cmd(session_id: str, project_dir: Path) -> None:
    """Remove every recorded worktree directory for the session.

    Iterates ``session.runtime_state.worktrees`` and calls
    :func:`tripwire.core.git_helpers.worktree_remove` for each. Errors
    are reported but never abort the loop — filesystem deletion is
    best-effort.
    """
    _, session = _resolve_and_load_session(project_dir, session_id)

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    removed: list[str] = []
    errors: list[str] = []
    for wt in session.runtime_state.worktrees:
        try:
            worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
            removed.append(wt.worktree_path)
        except (subprocess.SubprocessError, OSError) as exc:
            # Best-effort: filesystem deletion errors and subprocess
            # blow-ups are reported but never abort the loop.
            errors.append(f"{wt.worktree_path}: {exc}")

    for wt_path in removed:
        click.echo(f"removed worktree: {wt_path}")
    for err in errors:
        click.echo(f"warning: {err}", err=True)
    if not removed and not errors:
        click.echo(f"session {session_id}: no worktrees to remove")
