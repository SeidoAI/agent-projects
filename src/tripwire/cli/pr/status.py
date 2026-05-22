"""``tripwire pr status`` — latest pm-review verdict for a session.

Read-only — never mutates events log or artifacts. Reads
``pm_review.completed`` events emitted by
:mod:`tripwire.core.pm_review.runner` and renders the most recent
verdict for a session along with the per-check outcomes.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.pr._group import pr_cmd
from tripwire.core.events.log import read_events
from tripwire.core.pm_review.checks import PM_REVIEW_CHECKS


@pr_cmd.command(name="status")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def pr_status_cmd(session_id: str, project_dir: Path) -> None:
    """Print the latest pm-review verdict for SESSION_ID.

    Exits 0 when a verdict is found, 1 when no ``pm_review.completed``
    event exists for the session.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = list(
        read_events(
            resolved,
            workflow="pm-review",
            instance=session_id,
            event="pm_review.completed",
        )
    )
    if not rows:
        raise click.ClickException(
            f"no pm-review found for session {session_id!r}; run pm-review first."
        )

    latest = rows[-1]
    details = latest.get("details") or {}
    outcome = details.get("outcome", "unknown")
    failed = list(details.get("failed_checks") or [])
    passed = list(details.get("passed_checks") or [])
    ts = latest.get("ts", "")

    click.echo(f"pm-review status: {outcome}")
    click.echo(f"  session: {session_id}")
    click.echo(f"  reviewed_at: {ts}")
    click.echo("")
    click.echo("Checks:")
    # Render in the canonical pm-review check order so PMs see a
    # consistent layout across sessions; checks the verdict didn't
    # mention drop to "unknown" so it's obvious when a feeder check
    # hasn't reported.
    failed_set = set(failed)
    passed_set = set(passed)
    for name, _validator_id in PM_REVIEW_CHECKS:
        if name in failed_set:
            click.echo(f"  ✗ {name}: fail")
        elif name in passed_set:
            click.echo(f"  ✓ {name}: pass")
        else:
            click.echo(f"  ? {name}: unknown")
    if outcome != "auto-merge":
        click.echo("")
        click.echo(f"Failed checks: {', '.join(failed) if failed else '(none)'}")


__all__ = ["pr_status_cmd"]
