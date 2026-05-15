"""``tripwire gh`` CLI — Layer-1 wrappers around the ``gh`` cli.

Thin click adapters that match the side-effect handler bodies in
:mod:`tripwire.core.workflow.side_effects` one-to-one. They exist so an
operator can replay a single ``gh`` interaction (mark a PR ready, undo
it, close one) without driving a full workflow transition.

Subcommands:

- ``pr-ready <num>``      — ``gh pr ready <num>``
- ``pr-ready-undo <num>`` — ``gh pr ready <num> --undo``
- ``pr-close <num>``      — ``gh pr close <num>`` via the canonical
  :func:`tripwire.core.session_abandon._close_pr_by_num` helper.

All three delegate their subprocess plumbing to
:mod:`tripwire.core.gh_helpers`.
"""

from __future__ import annotations

import click

from tripwire.core.gh_helpers import GhError, gh_pr_ready


@click.group(name="gh")
def gh_cmd() -> None:
    """Low-level GitHub CLI helpers exposed as Layer-1 CLI commands."""


def _gh_pr_ready(pr_num: int, *, undo: bool) -> tuple[bool, str]:
    """Run ``gh pr ready <num>`` (with optional ``--undo``).

    Returns ``(ok, error_message)`` — ``ok`` is True when gh succeeded;
    on failure ``error_message`` is the formatted ``GhError`` (which
    already carries the original stderr and exit code, in the
    ``"gh pr ready 42 exit=K: <stderr>"`` shape). The CLI wrappers
    surface that string in their click error.
    """
    try:
        gh_pr_ready(pr_num, undo=undo)
    except GhError as exc:
        return False, str(exc)
    return True, ""


@gh_cmd.command("pr-ready")
@click.argument("pr_num", type=int)
def gh_pr_ready_cmd(pr_num: int) -> None:
    """Mark PR ``pr_num`` as ready-for-review.

    Equivalent to ``gh pr ready <num>``. Non-zero ``gh`` exits surface
    as a click error so callers can detect failures; a previously-ready
    PR exits clean (idempotent at the gh level).
    """
    ok, err = _gh_pr_ready(pr_num, undo=False)
    if not ok:
        # ``err`` already includes the gh exit code + stderr in its
        # ``GhError`` shape; we prefix with the per-PR framing the
        # test suite pinned in v0.13.
        raise click.ClickException(f"gh pr ready #{pr_num}: {err}")
    click.echo(f"marked PR #{pr_num} ready-for-review")


@gh_cmd.command("pr-ready-undo")
@click.argument("pr_num", type=int)
def gh_pr_ready_undo_cmd(pr_num: int) -> None:
    """Flip PR ``pr_num`` back to draft.

    Equivalent to ``gh pr ready <num> --undo``. Mirrors the
    ``flip_drafts_to_draft`` side-effect's per-PR step.
    """
    ok, err = _gh_pr_ready(pr_num, undo=True)
    if not ok:
        raise click.ClickException(f"gh pr ready --undo #{pr_num}: {err}")
    click.echo(f"flipped PR #{pr_num} back to draft")


@gh_cmd.command("pr-close")
@click.argument("pr_num", type=int)
def gh_pr_close_cmd(pr_num: int) -> None:
    """Close PR ``pr_num`` via ``gh pr close``.

    Delegates to :func:`tripwire.core.session_abandon._close_pr_by_num`,
    which captures errors on a verdict rather than raising — we surface
    them here as a click error if present.
    """
    from tripwire.core.session_abandon import _close_pr_by_num

    verdict = _close_pr_by_num(pr_num)
    if verdict.error:
        raise click.ClickException(verdict.error)
    click.echo(f"closed PR #{pr_num}")
