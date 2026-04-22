"""`tripwire session` — session lifecycle and agenda operations.

Sessions live at `sessions/<id>/session.yaml`.

Subcommands:
- `list` — enumerate all sessions with status and issue counts
- `show <id>` — print one session's full YAML frontmatter + body
- `check <id>` — readiness punch list
- `queue <id>` — validate readiness, transition to queued
- `spawn <id>` — create worktree, launch claude -p, transition to executing
- `pause <id>` — SIGTERM the claude process, transition to paused
- `abandon <id>` — kill if running, transition to abandoned
- `cleanup [<id>]` — remove worktrees for completed/abandoned sessions
- `agenda` — session dependency DAG with launch recommendations
- `progress` — task-checklist rollup across active sessions
- `derive-branch <id>` — print canonical branch name
- `artifacts <id>` — alias for `tripwire artifacts list <id>`
"""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid as _uuid_mod
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.artifacts import artifacts_list
from tripwire.core.git_helpers import (
    worktree_add,
    worktree_is_dirty,
    worktree_path_for_session,
    worktree_prune,
    worktree_remove,
)
from tripwire.core.process_helpers import is_alive, send_sigterm
from tripwire.core.session_readiness import check_readiness
from tripwire.core.session_store import list_sessions, load_session, save_session
from tripwire.models.session import AgentSession, EngagementEntry, WorktreeEntry

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

    from tripwire.core.session_store import session_yaml_path

    yaml_path = session_yaml_path(resolved, session_id)
    click.echo(yaml_path.read_text(encoding="utf-8"))


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
    try:
        report = check_readiness(resolved, session_id, kind="check")
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    items = report.items
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
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    active_states = {"queued", "executing", "active"}
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
    from tripwire.core.branch_naming import BranchNameError, derive_branch_name
    from tripwire.core.store import load_issue

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


# ---------------------------------------------------------------------------
# queue / spawn / pause / abandon / cleanup / agenda
# ---------------------------------------------------------------------------


@session_cmd.command("queue")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_queue_cmd(session_id: str, project_dir: Path) -> None:
    """Validate readiness and transition session to queued."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if session.status != "planned":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'planned' to queue"
        )

    report = check_readiness(resolved, session_id, kind="queue")
    if not report.ready:
        for item in report.items:
            if not item.passing:
                click.echo(f"  ✗ {item.label}")
                if item.fix_hint:
                    click.echo(f"    → {item.fix_hint}")
        raise click.ClickException("Not ready to queue — fix errors above")

    session.status = "queued"
    session.updated_at = datetime.now(tz=timezone.utc)
    save_session(resolved, session)
    click.echo(f"Session '{session_id}' → queued")


def _resolve_clone_path(project_dir: Path, repo_slug: str) -> Path | None:
    """Look up the local clone path for a repo from project.yaml."""
    from tripwire.core.store import load_project

    try:
        project = load_project(project_dir)
    except Exception:
        return None
    if not project.repos or not isinstance(project.repos, dict):
        return None
    repo_cfg = project.repos.get(repo_slug)
    if repo_cfg is None:
        return None
    local = getattr(repo_cfg, "local", None)
    if local is None:
        return None
    p = Path(local).expanduser()
    return p if p.exists() else None


@session_cmd.command("spawn")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option("--max-turns-override", type=int, default=None)
@click.option("--log-dir", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.option("--resume", "resume_flag", is_flag=True, default=False)
def session_spawn_cmd(
    session_id: str,
    project_dir: Path,
    max_turns_override: int | None,
    log_dir: Path | None,
    dry_run: bool,
    resume_flag: bool,
) -> None:
    """Prep worktrees + skills + CLAUDE.md, then dispatch to the
    configured runtime to launch the agent. Transitions to executing."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.prep import run as prep_run

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"session '{session_id}' not found"
        ) from exc

    # Status gate
    if resume_flag:
        if session.status not in ("failed", "paused"):
            raise click.ClickException(
                f"--resume requires status 'failed' or 'paused', got '{session.status}'"
            )
    else:
        if session.status != "queued":
            raise click.ClickException(
                f"session '{session_id}' is '{session.status}', must be 'queued' to spawn"
            )

    if not shutil.which("claude"):
        raise click.ClickException("claude CLI not found on PATH")

    # Resolve runtime from spawn config
    resolved_spawn = load_resolved_spawn_config(resolved, session=session)
    try:
        runtime = get_runtime(resolved_spawn.invocation.runtime)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Prep (runtime-agnostic): worktrees + skills + CLAUDE.md + kickoff
    try:
        prepped = prep_run(
            session=session,
            project_dir=resolved,
            runtime=runtime,
            max_turns_override=max_turns_override,
            claude_session_id=(
                session.runtime_state.claude_session_id if resume_flag else None
            ),
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(f"Dry run — would spawn session '{session_id}'")
        click.echo(f"  Runtime: {runtime.name}")
        for wt in prepped.worktrees:
            click.echo(f"  Worktree: {wt.worktree_path}")
        click.echo(f"  Max turns: {prepped.spawn_defaults.config.max_turns}")
        return

    # Launch via the runtime
    start_result = runtime.start(prepped)

    now = datetime.now(tz=timezone.utc)
    session.status = "executing"
    session.runtime_state.worktrees = start_result.worktrees
    session.runtime_state.claude_session_id = start_result.claude_session_id
    session.runtime_state.tmux_session_name = start_result.tmux_session_name
    session.runtime_state.pid = start_result.pid
    session.runtime_state.started_at = start_result.started_at
    session.runtime_state.log_path = start_result.log_path
    session.updated_at = now
    session.engagements.append(
        EngagementEntry(
            started_at=now,
            trigger="re_engagement" if resume_flag else "initial_launch",
        )
    )
    save_session(resolved, session)

    click.echo(
        f"Session '{session_id}' → executing  (runtime: {runtime.name})"
    )
    click.echo(f"  Branch: {prepped.worktrees[0].branch}")
    click.echo(f"  Code worktree: {prepped.code_worktree}")
    if start_result.tmux_session_name:
        click.echo(
            f"  Tmux session: {start_result.tmux_session_name}"
        )
        click.echo(f"\n  tripwire session attach {session_id}")
    if start_result.pid:
        click.echo(f"  PID: {start_result.pid}")
    click.echo(f"  Claude session: {start_result.claude_session_id}")


@session_cmd.command("attach")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_attach_cmd(session_id: str, project_dir: Path) -> None:
    """Attach to a running session. Behaviour is runtime-specific:
    tmux runtimes exec `tmux attach`; manual runtimes print the
    command to run."""
    import os

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"session '{session_id}' not found"
        ) from exc

    spawn = load_resolved_spawn_config(resolved, session=session)
    try:
        runtime = get_runtime(spawn.invocation.runtime)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    cmd = runtime.attach_command(session)
    if isinstance(cmd, AttachExec):
        os.execvp(cmd.argv[0], cmd.argv)
    elif isinstance(cmd, AttachInstruction):
        click.echo(cmd.message)
    else:
        raise click.ClickException(
            f"Runtime '{runtime.name}' returned unexpected attach command."
        )


@session_cmd.command("pause")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_pause_cmd(session_id: str, project_dir: Path) -> None:
    """Pause the session via its runtime, transition to paused."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if session.status != "executing":
        raise click.ClickException(
            f"session '{session_id}' is '{session.status}', must be 'executing' to pause"
        )

    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime_name = spawn.invocation.runtime
    now = datetime.now(tz=timezone.utc)

    # v0.7 legacy fallback: session has pid but no tmux_session_name.
    if (
        runtime_name == "tmux"
        and not session.runtime_state.tmux_session_name
        and session.runtime_state.pid
    ):
        pid = session.runtime_state.pid
        if pid and is_alive(pid):
            send_sigterm(pid)
            session.status = "paused"
            click.echo(
                f"Session '{session_id}' → paused (legacy SIGTERM to PID {pid})"
            )
        else:
            session.status = "failed"
            click.echo(
                f"Warning: PID {pid} not found — session '{session_id}' → failed"
            )
    else:
        runtime = get_runtime(runtime_name)
        runtime.pause(session)
        session.status = "paused"
        click.echo(f"Session '{session_id}' → paused")

    session.updated_at = now
    save_session(resolved, session)


@session_cmd.command("abandon")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Kill the session's runtime handle if running, transition to abandoned."""
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if session.status in ("completed", "abandoned"):
        raise click.ClickException(
            f"session '{session_id}' is already '{session.status}'"
        )

    spawn = load_resolved_spawn_config(resolved, session=session)
    runtime_name = spawn.invocation.runtime

    # v0.7 legacy fallback: session has pid but no tmux_session_name.
    if (
        runtime_name == "tmux"
        and not session.runtime_state.tmux_session_name
        and session.runtime_state.pid
    ):
        pid = session.runtime_state.pid
        if pid and session.status == "executing" and is_alive(pid):
            send_sigterm(pid)
            click.echo(f"Sent SIGTERM to PID {pid}")
    else:
        runtime = get_runtime(runtime_name)
        if session.status == "executing":
            runtime.abandon(session)

    session.status = "abandoned"
    session.updated_at = datetime.now(tz=timezone.utc)
    save_session(resolved, session)
    click.echo(f"Session '{session_id}' → abandoned")


@session_cmd.command("cleanup")
@click.argument("session_id", required=False, default=None)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--all",
    "clean_all",
    is_flag=True,
    default=False,
    help="Clean ALL session worktrees",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Skip dirty-worktree check",
)
def session_cleanup_cmd(
    session_id: str | None,
    project_dir: Path,
    clean_all: bool,
    force: bool,
) -> None:
    """Remove worktrees for completed/abandoned sessions."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    clones_to_prune: set[str] = set()

    if session_id:
        targets = [s for s in sessions if s.id == session_id]
        if not targets:
            raise click.ClickException(f"session '{session_id}' not found")
    elif clean_all:
        if not click.confirm("Remove ALL session worktrees?"):
            return
        targets = sessions
    else:
        targets = [s for s in sessions if s.status in ("completed", "abandoned")]

    cleaned = 0
    for session in targets:
        for wt in session.runtime_state.worktrees:
            wt_path = Path(wt.worktree_path)
            if not wt_path.exists():
                continue
            if not force and worktree_is_dirty(wt_path):
                click.echo(f"  Skipping {wt_path} — uncommitted changes (use --force)")
                continue
            clone_path = Path(wt.clone_path)
            worktree_remove(clone_path, wt_path)
            clones_to_prune.add(str(clone_path))
            cleaned += 1

        # Clear removed worktrees from runtime_state
        if session.runtime_state.worktrees:
            remaining = [
                wt
                for wt in session.runtime_state.worktrees
                if Path(wt.worktree_path).exists()
            ]
            session.runtime_state.worktrees = remaining
            save_session(resolved, session)

    for clone_str in clones_to_prune:
        worktree_prune(Path(clone_str))

    click.echo(f"Cleaned {cleaned} worktree(s)")


@session_cmd.command("agenda")
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
@click.option("--status", "filter_status", default=None)
def session_agenda_cmd(
    project_dir: Path, output_format: str, filter_status: str | None
) -> None:
    """Session dependency DAG with launch recommendations."""
    from tripwire.core.session_agenda import CycleDetectedError, build_agenda

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    if filter_status:
        sessions = [s for s in sessions if s.status == filter_status]
    if not sessions:
        click.echo("No sessions found.")
        return

    session_dicts = [
        {
            "id": s.id,
            "status": s.status,
            "blocked_by_sessions": s.blocked_by_sessions,
        }
        for s in sessions
    ]

    try:
        report = build_agenda(session_dicts)
    except CycleDetectedError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        payload = {
            "totals": report.totals,
            "critical_path": report.critical_path,
            "sessions": [
                {
                    "id": info.id,
                    "status": info.status,
                    "blocked_by": info.blocked_by,
                    "dependents": info.dependents,
                    "is_launchable": info.is_launchable,
                    "critical_path_position": info.critical_path_position,
                }
                for info in (
                    report.launchable
                    + report.blocked
                    + report.in_flight
                    + report.completed_sessions
                )
            ],
            "recommendations": [asdict(r) for r in report.recommendations],
            "warnings": report.warnings,
        }
        click.echo(json.dumps(payload, indent=2))
        return

    # Text output
    from tripwire.core.store import load_project as _lp

    try:
        proj = _lp(resolved)
        proj_name = proj.name
    except Exception:
        proj_name = "project"

    total_count = sum(report.totals.values())
    click.echo(f"{proj_name} — {total_count} sessions")
    parts = []
    for status, count in sorted(report.totals.items()):
        parts.append(f"{count} {status}")
    click.echo(f"  {', '.join(parts)}")

    if report.all_completed:
        click.echo("\nAll sessions complete.")
        return

    if report.critical_path and len(report.critical_path) > 1:
        cp = " → ".join(report.critical_path)
        click.echo(f"\n  critical path: {cp} ({len(report.critical_path)} sessions)")

    if report.launchable:
        click.echo("\nLAUNCHABLE (all blockers completed):")
        for info in report.launchable:
            blocker_text = "no blockers" if not info.blocked_by else "blockers done"
            click.echo(f"  {info.id:<30} {info.status:<10} {blocker_text}")

    if report.in_flight:
        click.echo("\nIN FLIGHT:")
        for info in report.in_flight:
            click.echo(f"  {info.id:<30} {info.status}")

    if report.blocked:
        click.echo("\nBLOCKED:")
        for info in report.blocked:
            click.echo(
                f"  {info.id:<30} {info.status:<10} blocked by: {', '.join(info.blocked_by)}"
            )

    if report.recommendations:
        click.echo("\nRecommended next:")
        for rec in report.recommendations:
            click.echo(f"  {rec.rank}. {rec.session_id}  ({rec.rationale})")

    if report.warnings:
        click.echo("\nWarnings:")
        for w in report.warnings:
            click.echo(f"  ⚠ {w}")


# Alias `tripwire session artifacts <id>` to the existing `tripwire artifacts list <id>`.
session_cmd.add_command(artifacts_list, name="artifacts")


# ----------------------------------------------------------------------------
# `tripwire session complete` — close-out orchestration
# ----------------------------------------------------------------------------


@session_cmd.command("complete")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--dry-run", is_flag=True, default=False)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Bypass all gates (use sparingly).",
)
@click.option(
    "--force-review",
    is_flag=True,
    default=False,
    help="Proceed even if the most recent review failed or was never run.",
)
@click.option("--skip-artifact-check", is_flag=True, default=False)
@click.option("--skip-worktree-cleanup", is_flag=True, default=False)
@click.option("--skip-pr-merge-check", is_flag=True, default=False)
@click.option(
    "--skip-pr-flow",
    is_flag=True,
    default=False,
    help="Skip the dual-PR commit/push/create flow.",
)
@click.option(
    "--skip-pr-flow-push",
    is_flag=True,
    default=False,
    help="Run the PR flow but skip `git push` (useful when PRs already exist).",
)
def session_complete_cmd(
    session_id: str,
    project_dir: Path,
    dry_run: bool,
    force: bool,
    force_review: bool,
    skip_artifact_check: bool,
    skip_worktree_cleanup: bool,
    skip_pr_merge_check: bool,
    skip_pr_flow: bool,
    skip_pr_flow_push: bool,
) -> None:
    """Complete a session: verify gates, open dual PRs, close issues, cleanup."""
    from tripwire.core.session_complete import (
        CompleteError,
        complete_session,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = complete_session(
            resolved,
            session_id,
            dry_run=dry_run,
            force=force,
            force_review=force_review,
            skip_artifact_check=skip_artifact_check,
            skip_worktree_cleanup=skip_worktree_cleanup,
            skip_pr_merge_check=skip_pr_merge_check,
            skip_pr_flow=skip_pr_flow,
            skip_pr_flow_push=skip_pr_flow_push,
        )
    except CompleteError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(f"Dry run: session {session_id} can be completed.")
        if result.node_diffs:
            click.echo(f"  Node diffs to review: {len(result.node_diffs)}")
        return

    click.echo(f"Session {session_id} → done")
    for iss in result.issues_closed:
        click.echo(f"  closed: {iss}")
    for wt in result.worktrees_removed:
        click.echo(f"  removed worktree: {wt}")


# ----------------------------------------------------------------------------
# `tripwire session review` — PR diff vs. issue specs
# ----------------------------------------------------------------------------


def _gather_pr_number(session) -> int | None:
    import json as _json

    for wt in session.runtime_state.worktrees:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    wt.branch,
                    "--json",
                    "number",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = _json.loads(result.stdout)
                if prs:
                    return int(prs[0]["number"])
        except (subprocess.SubprocessError, OSError, _json.JSONDecodeError):
            continue
    return None


def _gather_pr_files(pr_number: int) -> list[str]:
    import json as _json

    try:
        result = subprocess.run(
            ["gh", "pr", "view", str(pr_number), "--json", "files"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            data = _json.loads(result.stdout)
            return [f["path"] for f in data.get("files", [])]
    except (subprocess.SubprocessError, OSError, _json.JSONDecodeError):
        pass
    return []


def _render_verified_md(
    *, issue, criteria: list[str], verdict: str, stamp: str, deviations: list[str]
) -> str:
    """Render the shipped verified.md.j2 template with review context."""
    from jinja2 import Environment, FileSystemLoader

    import tripwire

    template_root = Path(tripwire.__file__).parent / "templates" / "issue_artifacts"
    env = Environment(
        loader=FileSystemLoader(str(template_root)),
        keep_trailing_newline=True,
    )
    template = env.get_template("verified.md.j2")
    return template.render(
        issue=issue,
        criteria=criteria,
        verdict=verdict,
        verified_by="pm-agent",
        verified_at=stamp,
        deviations=deviations,
    )


def _write_verified_for_session(project_dir: Path, session, report) -> None:
    """For each issue in the session, write or append issues/<key>/verified.md.

    New file: rendered via ``templates/issue_artifacts/verified.md.j2``.
    Existing file: append a ``## Re-review <date>`` section preserving history.
    """
    from tripwire.core import paths as _paths
    from tripwire.core.store import load_issue

    stamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    for ir in report.issue_reviews:
        verified_path = _paths.issue_dir(project_dir, ir.key) / "verified.md"
        if verified_path.is_file():
            existing = verified_path.read_text(encoding="utf-8")
            addition = (
                f"\n\n## Re-review {stamp} (session {session.id})\n"
                f"Verdict: {report.verdict}\n"
            )
            verified_path.write_text(existing + addition, encoding="utf-8")
            continue

        try:
            issue = load_issue(project_dir, ir.key)
        except FileNotFoundError:
            continue
        rendered = _render_verified_md(
            issue=issue,
            criteria=ir.criteria,
            verdict=report.verdict,
            stamp=stamp,
            deviations=report.deviations.unspec_files,
        )
        verified_path.parent.mkdir(parents=True, exist_ok=True)
        verified_path.write_text(rendered, encoding="utf-8")


@session_cmd.command("review")
@click.argument("session_id")
@click.option(
    "--pr",
    "pr_number",
    type=int,
    default=None,
    help="PR number (auto-detected from worktree branch if omitted).",
)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
@click.option(
    "--post-pr-comments/--no-post-pr-comments",
    default=False,
    help="Post review findings as a PR comment via `gh`.",
)
@click.option(
    "--write-verified/--no-write-verified",
    default=True,
    help="Write/update issues/<key>/verified.md for each issue in the session.",
)
def session_review_cmd(
    session_id: str,
    pr_number: int | None,
    project_dir: Path,
    output_format: str,
    post_pr_comments: bool,
    write_verified: bool,
) -> None:
    """Review a session's PR against the session's issue specs."""
    import json as _json
    from dataclasses import asdict

    from tripwire.core import paths as _paths
    from tripwire.core.session_review import (
        IssueReview,
        ReviewReport,
        check_plan_adherence,
        detect_deviations,
        parse_acceptance_criteria,
        parse_repo_scope,
    )
    from tripwire.core.store import load_issue

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    session = load_session(resolved, session_id)

    if pr_number is None:
        pr_number = _gather_pr_number(session)

    pr_files = _gather_pr_files(pr_number) if pr_number is not None else []

    report = ReviewReport(session_id=session_id, pr_number=pr_number)

    scope_paths: list[str] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(resolved, issue_key)
        except FileNotFoundError:
            continue
        criteria = parse_acceptance_criteria(issue.body)
        report.issue_reviews.append(
            IssueReview(
                key=issue_key,
                criteria=criteria,
                criteria_met=[False] * len(criteria),
                criteria_evidence=[None] * len(criteria),
            )
        )
        scope_paths.extend(parse_repo_scope(issue.body))

    devs = detect_deviations(pr_files, scope_paths)
    report.deviations.unspec_files = devs["unspec_files"]

    plan_path = _paths.session_plan_path(resolved, session_id)
    if plan_path.is_file():
        ok, unmatched = check_plan_adherence(
            plan_path.read_text(encoding="utf-8"), pr_files
        )
        report.plan_adherence_ok = ok
        report.plan_unmatched_steps = unmatched

    if report.deviations.unspec_files or not report.plan_adherence_ok:
        report.verdict = "approved_with_notes"

    if output_format == "json":
        click.echo(_json.dumps(asdict(report), indent=2, default=str))
    else:
        click.echo(
            f"Session Review: {session_id} (PR "
            f"{f'#{pr_number}' if pr_number else 'not found'})\n"
        )
        click.echo(f"Verdict: {report.verdict}")
        click.echo("\nIssues:")
        for ir in report.issue_reviews:
            click.echo(
                f"  {ir.key}: {len(ir.criteria)} criteria (manual verification needed)"
            )
        if report.deviations.unspec_files:
            click.echo("\nDeviations (unspec'd files):")
            for f in report.deviations.unspec_files:
                click.echo(f"  - {f}")
        if report.plan_unmatched_steps:
            click.echo("\nPlan adherence issues:")
            for s in report.plan_unmatched_steps:
                click.echo(f"  - {s} (named in plan, absent from PR)")

    if post_pr_comments and pr_number:
        comment_lines = [
            "## Tripwire session review",
            "",
            f"Verdict: `{report.verdict}`",
        ]
        if report.deviations.unspec_files:
            comment_lines.append("")
            comment_lines.append("**Files outside issue scope:**")
            for f in report.deviations.unspec_files:
                comment_lines.append(f"- `{f}`")
        try:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "comment",
                    str(pr_number),
                    "--body",
                    "\n".join(comment_lines),
                ],
                check=True,
                capture_output=True,
            )
            if output_format == "text":
                click.echo(f"\n(posted to PR #{pr_number})")
        except (subprocess.SubprocessError, OSError):
            if output_format == "text":
                click.echo(f"\n(failed to post to PR #{pr_number})")

    if write_verified:
        _write_verified_for_session(resolved, session, report)

    # Write review.json artifact for session_complete's review-exit-code gate
    # (spec §11.2 step 4). Always — regardless of output_format or other flags —
    # so that subsequent `session complete` can consult a deterministic record.
    _write_review_json(resolved, session, report)

    raise click.exceptions.Exit(report.exit_code)


def _write_review_json(project_dir: Path, session, report) -> None:
    """Persist sessions/<id>/review.json for the complete-time gate."""
    import json as _json

    review_path = project_dir / "sessions" / session.id / "review.json"
    review_path.parent.mkdir(parents=True, exist_ok=True)

    head_sha = None
    if session.runtime_state.worktrees:
        wt_path = Path(session.runtime_state.worktrees[0].worktree_path)
        if wt_path.is_dir():
            try:
                result = subprocess.run(
                    ["git", "-C", str(wt_path), "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    head_sha = result.stdout.strip() or None
            except (subprocess.SubprocessError, OSError):
                pass

    payload = {
        "session_id": session.id,
        "verdict": report.verdict,
        "exit_code": report.exit_code,
        "pr_number": report.pr_number,
        "head_sha": head_sha,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }
    review_path.write_text(_json.dumps(payload, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------
# `tripwire session monitor` — one-shot runtime snapshot
# ----------------------------------------------------------------------------


@session_cmd.command("monitor")
@click.argument("session_ids", nargs=-1)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def session_monitor_cmd(
    session_ids: tuple[str, ...], project_dir: Path, output_format: str
) -> None:
    """One-shot runtime snapshot. With no args, monitors all executing sessions.

    The PM's `/pm-session-monitor` slash command wraps this in a self-paced
    loop via ScheduleWakeup.
    """
    from dataclasses import asdict

    from tripwire.core.session_monitor import take_snapshot

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    if session_ids:
        sessions = [s for s in sessions if s.id in session_ids]
    else:
        sessions = [s for s in sessions if s.status == "executing"]

    if not sessions:
        click.echo("No executing sessions.")
        return

    snaps = [take_snapshot(resolved, s.id) for s in sessions]

    if output_format == "json":
        click.echo(json.dumps([asdict(s) for s in snaps], indent=2, default=str))
        return

    for snap in snaps:
        click.echo(f"{snap.session_id}  {snap.status}  source={snap.source}")
        if snap.turn is not None:
            click.echo(f"  turn: {snap.turn}")
        if snap.total_cost_usd is not None:
            click.echo(f"  cost: ${snap.total_cost_usd:.2f}")
        if snap.latest_tool:
            click.echo(f"  latest tool: {snap.latest_tool}")
        if snap.branch:
            pr = f" (PR #{snap.pr_number})" if snap.pr_number else ""
            click.echo(f"  branch: {snap.branch}{pr}")
        if snap.errors:
            for err in snap.errors[-3:]:
                click.echo(f"  error: {err}")
        if snap.stuck:
            click.echo("  ⚑ STUCK (no log activity in 10min)")
        if snap.process_alive is False:
            click.echo("  ⚑ PROCESS DEAD")
        click.echo()


# ----------------------------------------------------------------------------
# `tripwire session insights` — review / apply / reject agent node proposals
# ----------------------------------------------------------------------------


@session_cmd.group(name="insights")
def session_insights_cmd() -> None:
    """Review and apply session-proposed concept-node insights."""


@session_insights_cmd.command("list")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def session_insights_list_cmd(
    session_id: str, project_dir: Path, output_format: str
) -> None:
    """List node proposals from a session's insights.yaml."""
    from tripwire.core.insights_store import load_insights

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    if output_format == "json":
        click.echo(insights.model_dump_json(indent=2, exclude_none=True))
        return

    if not insights.proposals:
        click.echo("No insight proposals.")
        return

    for p in insights.proposals:
        click.echo(f"{p.kind} {p.id}")
        if p.kind == "new_node":
            click.echo(f"  name: {p.name}")
        else:
            click.echo(f"  delta: {p.delta}")
        click.echo(f"  rationale: {p.rationale}")
        click.echo("")


@session_insights_cmd.command("apply")
@click.argument("session_id")
@click.option(
    "--proposal",
    "proposal_id",
    required=True,
    help="The proposal id to apply",
)
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_apply_cmd(
    session_id: str, proposal_id: str, project_dir: Path
) -> None:
    """Materialise a proposal: new_node writes nodes/<id>.yaml; update_node appends delta."""
    from datetime import datetime as _dt
    from datetime import timezone as _tz

    from tripwire.core.insights_store import load_insights, save_insights
    from tripwire.core.node_store import load_node, save_node
    from tripwire.models import ConceptNode

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    if proposal.kind == "new_node":
        # `type` is required on new_node proposals (enforced by the model
        # validator); no hardcoded fallback here.
        node = ConceptNode(
            id=proposal.id,
            type=proposal.type,
            name=proposal.name or proposal.id,
            status="active",
            body=proposal.body or "",
            related=proposal.related,
        )
        save_node(resolved, node, update_cache=False)
        click.echo(f"Created node {proposal.id} (type={proposal.type})")
    else:
        try:
            node = load_node(resolved, proposal.id)
        except FileNotFoundError as exc:
            raise click.ClickException(
                f"Cannot apply update: node {proposal.id!r} does not exist."
            ) from exc
        stamp = _dt.now(tz=_tz.utc).strftime("%Y-%m-%d")
        new_body = (
            node.body.rstrip()
            + f"\n\n## Updated {stamp} (session {session_id})\n{proposal.delta}\n"
        )
        save_node(
            resolved,
            node.model_copy(update={"body": new_body}),
            update_cache=False,
        )
        click.echo(f"Updated node {proposal.id}")

    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(
        resolved,
        session_id,
        insights.model_copy(update={"proposals": remaining}),
    )


@session_insights_cmd.command("reject")
@click.argument("session_id")
@click.option("--proposal", "proposal_id", required=True)
@click.option("--reason", default="", help="Why rejected (for audit)")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
def session_insights_reject_cmd(
    session_id: str, proposal_id: str, reason: str, project_dir: Path
) -> None:
    """Drop a proposal from insights.yaml and record it in insights.rejected.yaml."""
    from tripwire.core.insights_store import (
        load_insights,
        record_rejection,
        save_insights,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    insights = load_insights(resolved, session_id)

    proposal = next((p for p in insights.proposals if p.id == proposal_id), None)
    if proposal is None:
        raise click.ClickException(f"Unknown proposal id {proposal_id!r}")

    record_rejection(resolved, session_id, proposal_id, reason)
    remaining = [p for p in insights.proposals if p.id != proposal_id]
    save_insights(
        resolved,
        session_id,
        insights.model_copy(update={"proposals": remaining}),
    )
    click.echo(f"Rejected proposal {proposal_id}")
