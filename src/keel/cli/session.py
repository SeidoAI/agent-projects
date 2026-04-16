"""`keel session` — read-only operations on agent sessions.

Sessions live at `sessions/<id>/session.yaml`. In v0 agents write session
files directly; the CLI provides only browsing.

Subcommands:
- `list` — enumerate all sessions with status and issue counts
- `show <id>` — print one session's full YAML frontmatter + body
- `artifacts <id>` — alias for `keel artifacts list <id>`
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from keel.cli._utils import require_project as _require_project
from keel.cli.artifacts import artifacts_list
from keel.core.session_store import list_sessions, load_session

console = Console()


@dataclass
class SessionSummary:
    id: str
    name: str
    agent: str
    status: str
    issue_count: int
    repo_count: int


@click.group(name="session")
def session_cmd() -> None:
    """Session operations (read-only in v0)."""


@session_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def session_list_cmd(project_dir: Path, output_format: str) -> None:
    """List every session in the project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    summaries = [
        SessionSummary(
            id=s.id,
            name=s.name,
            agent=s.agent,
            status=s.status,
            issue_count=len(s.issues),
            repo_count=len(s.repos),
        )
        for s in sessions
    ]

    if output_format == "json":
        click.echo(json.dumps([asdict(s) for s in summaries], indent=2))
        return

    if not summaries:
        console.print("[dim]no sessions yet[/dim]")
        return

    table = Table(title="Sessions", show_header=True)
    table.add_column("id")
    table.add_column("name")
    table.add_column("agent")
    table.add_column("status")
    table.add_column("issues", justify="right")
    table.add_column("repos", justify="right")
    for s in summaries:
        table.add_row(
            s.id,
            s.name,
            s.agent,
            s.status,
            str(s.issue_count),
            str(s.repo_count),
        )
    console.print(table)


@session_cmd.command("show")
@click.argument("session_id")
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
def session_show_cmd(session_id: str, project_dir: Path, output_format: str) -> None:
    """Print one session's YAML (text) or structured data (json)."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(session.model_dump_json(indent=2, exclude_none=True))
        return

    from keel.core.session_store import session_yaml_path

    yaml_path = session_yaml_path(resolved, session_id)
    click.echo(yaml_path.read_text(encoding="utf-8"))


@dataclass
class ReadinessItem:
    label: str
    passing: bool
    severity: str  # "error" | "warning"
    fix_hint: str | None = None


def _load_manifest_for_check(project_dir: Path):
    """Load ArtifactManifest; raises ClickException on parse failure."""
    import yaml as _yaml

    from keel.models.manifest import ArtifactManifest

    manifest_path = project_dir / "templates" / "artifacts" / "manifest.yaml"
    if not manifest_path.exists():
        raise click.ClickException(f"manifest.yaml not found at {manifest_path}")
    return ArtifactManifest.model_validate(
        _yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    )


def _compute_readiness(project_dir: Path, session_id: str) -> list[ReadinessItem]:
    """Compute launch-readiness for a session.

    Checks required planning artifacts (per manifest.yaml, owned_by=pm),
    blockers on the session's issues, handoff.yaml presence + validity.
    """
    from keel.core.handoff_store import handoff_exists, load_handoff
    from keel.core.store import load_issue

    items: list[ReadinessItem] = []

    try:
        session = load_session(project_dir, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    # Required planning artifacts owned by PM per manifest.
    manifest = _load_manifest_for_check(project_dir)
    sess_dir = project_dir / "sessions" / session_id
    for entry in manifest.artifacts:
        if entry.produced_at != "planning" or entry.owned_by != "pm":
            continue
        if not entry.required:
            continue
        present = (sess_dir / entry.file).is_file()
        items.append(
            ReadinessItem(
                label=f"planning artifact: {entry.file}",
                passing=present,
                severity="error",
                fix_hint=(
                    None if present else f"Write {entry.file} from {entry.template}"
                ),
            )
        )

    # Blockers on issues.
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            items.append(
                ReadinessItem(
                    label=f"issue {issue_key} referenced by session not found",
                    passing=False,
                    severity="error",
                )
            )
            continue
        for blocker_key in issue.blocked_by or []:
            try:
                blocker = load_issue(project_dir, blocker_key)
            except FileNotFoundError:
                items.append(
                    ReadinessItem(
                        label=f"blocker {blocker_key} referenced by {issue_key} not found",
                        passing=False,
                        severity="error",
                    )
                )
                continue
            if blocker.status != "done":
                items.append(
                    ReadinessItem(
                        label=f"blocker: {blocker_key} ({blocker.status})",
                        passing=False,
                        severity="error",
                        fix_hint=f"Wait for {blocker_key} to reach status=done",
                    )
                )

    # handoff.yaml presence + loadability.
    if not handoff_exists(project_dir, session_id):
        items.append(
            ReadinessItem(
                label="handoff.yaml present",
                passing=False,
                severity="error",
                fix_hint="Run /pm-session-launch to create handoff.yaml",
            )
        )
    else:
        try:
            load_handoff(project_dir, session_id)
            items.append(
                ReadinessItem(
                    label="handoff.yaml valid + branch per convention",
                    passing=True,
                    severity="error",
                )
            )
        except Exception as exc:
            items.append(
                ReadinessItem(
                    label=f"handoff.yaml invalid: {exc}",
                    passing=False,
                    severity="error",
                    fix_hint="Fix handoff.yaml to match schema",
                )
            )

    return items


@session_cmd.command("check")
@click.argument("session_id")
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
def session_check_cmd(session_id: str, project_dir: Path, output_format: str) -> None:
    """Report launch-readiness for a session — no state transition."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    items = _compute_readiness(resolved, session_id)
    errors = [i for i in items if not i.passing and i.severity == "error"]

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "session_id": session_id,
                    "launch_ready": len(errors) == 0,
                    "items": [asdict(i) for i in items],
                },
                indent=2,
            )
        )
    else:
        click.echo(f"Readiness for {session_id}:\n")
        for item in items:
            mark = "✓" if item.passing else "✗"
            click.echo(f"  {mark} {item.label}")
            if not item.passing and item.fix_hint:
                click.echo(f"    → {item.fix_hint}")
        click.echo()
        if errors:
            click.echo(f"{len(errors)} must-fix. Not launch-ready.")
        else:
            click.echo("Launch-ready.")
    if errors:
        raise click.exceptions.Exit(1)


def _parse_task_checklist(path: Path) -> tuple[int, int]:
    """Count ``- [ ]`` and ``- [x]`` checkboxes in a task-checklist markdown."""
    if not path.is_file():
        return 0, 0
    text = path.read_text(encoding="utf-8")
    total = text.count("- [ ]") + text.count("- [x]") + text.count("- [X]")
    done = text.count("- [x]") + text.count("- [X]")
    return total, done


def _days_since(when: datetime | None) -> int:
    """Approximate: days since ``when`` (UTC now - when)."""
    if when is None:
        return 0
    from datetime import timezone

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

    Active = session.status in {queued, implementing, verifying}.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    active_states = {"queued", "implementing", "verifying"}
    sessions = [s for s in list_sessions(resolved) if s.status in active_states]
    if focus:
        sessions = [s for s in sessions if focus in s.id]

    reports: list[dict] = []
    for s in sessions:
        checklist_path = resolved / "sessions" / s.id / "task-checklist.md"
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


@session_cmd.command("derive-branch")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_derive_branch_cmd(session_id: str, project_dir: Path) -> None:
    """Print the canonical branch name for a session.

    Format: <kind>/<session-slug> where kind is the primary issue's
    kind (first item in session.yaml.issues).
    """
    from keel.core.branch_naming import BranchNameError, derive_branch_name
    from keel.core.store import load_issue

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc
    if not session.issues:
        raise click.ClickException(
            f"session '{session_id}' has no issues; cannot derive branch"
        )
    primary_key = session.issues[0]
    try:
        issue = load_issue(resolved, primary_key)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"primary issue '{primary_key}' not found for session '{session_id}'"
        ) from exc
    try:
        click.echo(derive_branch_name(session_id, issue.kind))
    except BranchNameError as exc:
        raise click.ClickException(str(exc)) from exc


# Alias `keel session artifacts <id>` to the existing `keel artifacts list <id>`.
# Exposes session-related commands in one place instead of making users
# remember that artifact browsing sits under a separate top-level command.
session_cmd.add_command(artifacts_list, name="artifacts")
