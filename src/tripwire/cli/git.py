"""``tripwire git`` CLI — Layer-1 wrappers around :mod:`tripwire.core.git_helpers`.

Each subcommand is a thin click wrapper that lifts one side-effect's
body into a directly-invocable command. The workflow executor still
owns orchestration; these CLIs exist so an operator can replay or
rehearse any single step without spinning a transition.

Subcommands:

- ``rebase-pt <wt-path>`` — ``git fetch origin`` + ``rebase origin/main``
  inside the given worktree. Wraps
  :func:`tripwire.core.git_helpers.rebase_branch_onto`.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.group(name="git")
def git_cmd() -> None:
    """Low-level git helpers exposed as Layer-1 CLI commands."""


@git_cmd.command("rebase-pt")
@click.argument(
    "worktree_path",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True, exists=True),
)
def git_rebase_pt_cmd(worktree_path: Path) -> None:
    """Fetch origin then rebase the worktree's branch onto ``origin/main``.

    Used by the ``rebase_pt_branch`` side-effect for project-tracking
    worktrees on ``in_review`` entry. On a clean rebase the worktree's
    HEAD now sits atop ``origin/main``; on conflict the rebase is
    aborted and this command exits 1 with the conflict summary.
    """
    from tripwire.core.git_helpers import (
        RebaseConflict,
        fetch_origin,
        rebase_branch_onto,
    )

    resolved = worktree_path.expanduser().resolve()
    try:
        fetch_origin(resolved)
        rebase_branch_onto(resolved, "origin/main")
    except RebaseConflict as exc:
        raise click.ClickException(f"pt_rebase_conflict: {exc}") from exc
    click.echo(f"rebased {resolved} onto origin/main")
