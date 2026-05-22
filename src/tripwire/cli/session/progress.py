"""``tripwire session progress`` — task-checklist rollup across active sessions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_store import list_sessions
from tripwire.core.task_checklist import parse_task_checklist


def _parse_task_checklist(path: Path) -> tuple[int, int]:
    """Read a task-checklist file and return (total, done) row counts.

    Delegates to :func:`tripwire.core.task_checklist.parse_task_checklist`
    so CLI and UI agree on what counts as a task. The canonical template
    emits a Markdown table with a status column; bare-checkbox files
    that don't match the table format report (0, 0) and should migrate.
    """
    if not path.is_file():
        return 0, 0
    progress = parse_task_checklist(path.read_text(encoding="utf-8"))
    return progress.total, progress.done


def _days_since(when: datetime | None) -> int:
    """Approximate: days since ``when`` (UTC now - when)."""
    if when is None:
        return 0
    now = datetime.now(tz=timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (now - when).days


@session_cmd.command("progress")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option("--focus", default=None, help="Filter by session id substring.")
def session_progress_cmd(
    project_dir: Path, output_format: str, focus: str | None
) -> None:
    """Aggregate task-checklist status across active sessions.

    Active = session.status in {queued, executing, active}.
    """
    from tripwire.core import paths as _paths

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    active_states = {"queued", "executing", "active"}
    sessions = [s for s in list_sessions(resolved) if s.status in active_states]
    if focus:
        sessions = [s for s in sessions if focus in s.id]

    reports: list[dict] = []
    for s in sessions:
        checklist_path = _paths.session_dir(resolved, s.id) / "task-checklist.md"
        total, done = _parse_task_checklist(checklist_path)
        reports.append(
            {
                "session_id": s.id,
                "status": s.status,
                "tasks_total": total,
                "tasks_done": done,
                "days_in_status": _days_since(s.updated_at),
            }
        )

    if output_format == "json":
        click.echo(json.dumps(reports, indent=2))
        return

    if not reports:
        click.echo("No active sessions.")
        return
    for r in reports:
        click.echo(
            f"  {r['session_id']} ({r['status']}) — "
            f"{r['tasks_done']}/{r['tasks_total']} tasks, "
            f"{r['days_in_status']}d in status"
        )
