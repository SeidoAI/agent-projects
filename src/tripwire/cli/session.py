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


def _launch_claude(
    wt_path: Path,
    plan_content: str,
    session: AgentSession,
    project_dir: Path,
    session_name: str,
    branch_type: str,
    claude_session_id: str,
    max_turns: int,
    log_path: Path,
    project_slug: str,
    *,
    resume: bool = False,
) -> int:
    """Launch ``claude -p`` as a background process. Returns PID.

    Spawn args are built from the resolved spawn config (tripwire default
    ← project ← session overrides). `max_turns` is the CLI override that
    wins over any layer; if None, the resolved config's value is used.
    """
    from tripwire.core.spawn_config import (
        build_claude_args,
        load_resolved_spawn_config,
        render_prompt,
        render_system_append,
    )

    resolved = load_resolved_spawn_config(project_dir, session=session)
    # CLI max-turns override, if provided, takes final precedence.
    if max_turns is not None:
        resolved.config.max_turns = max_turns

    prompt = render_prompt(
        resolved,
        plan=plan_content,
        agent=session.agent,
        session_id=session.id,
        session_name=session_name,
        session_slug=session.id,
        branch_type=branch_type,
    )
    system_append = render_system_append(
        resolved,
        session_id=session.id,
        project_slug=project_slug,
    )
    args = build_claude_args(
        resolved,
        prompt=prompt,
        system_append=system_append,
        claude_session_id=claude_session_id,
        resume=resume,
    )

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "w")
    try:
        proc = subprocess.Popen(
            args,
            cwd=str(wt_path),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    finally:
        log_file.close()
    return proc.pid


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
    """Create worktree(s), launch claude -p, transition to executing."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

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

    # Claude on PATH
    if not shutil.which("claude"):
        raise click.ClickException("claude CLI not found on PATH")

    # Load plan
    from tripwire.core.paths import session_plan_path

    plan_path = session_plan_path(resolved, session_id)
    if not plan_path.is_file():
        raise click.ClickException(f"plan.md not found at {plan_path}")
    plan_content = plan_path.read_text(encoding="utf-8")

    # Load handoff for branch name
    from tripwire.core.handoff_store import load_handoff

    handoff = load_handoff(resolved, session_id)
    if handoff is None:
        raise click.ClickException("handoff.yaml not found")
    branch = handoff.branch

    # Parse branch type for PR title (e.g. "feat" from "feat/api-endpoints")
    from tripwire.core.branch_naming import parse_branch_name

    try:
        branch_type, _ = parse_branch_name(branch)
    except Exception:
        branch_type = "feat"

    # max_turns precedence: CLI override > agent YAML > 200
    agent_max_turns: int | None = None
    agent_yaml = resolved / "agents" / f"{session.agent}.yaml"
    if agent_yaml.is_file():
        import yaml as _yaml

        try:
            agent_data = _yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))
            if isinstance(agent_data, dict):
                agent_max_turns = agent_data.get("max_turns")
        except Exception:
            pass
    max_turns = max_turns_override or agent_max_turns or 200

    # Create worktrees (or reuse on --resume)
    worktree_entries: list[WorktreeEntry] = []
    primary_wt_path: Path | None = None

    if resume_flag and session.runtime_state.worktrees:
        for wt in session.runtime_state.worktrees:
            wt_path = Path(wt.worktree_path)
            if not wt_path.exists():
                raise click.ClickException(
                    f"Worktree {wt_path} no longer exists. "
                    f"Run 'tripwire session cleanup {session_id}' then spawn without --resume."
                )
            worktree_entries.append(wt)
            if primary_wt_path is None:
                primary_wt_path = wt_path
    else:
        for rb in session.repos:
            clone_path = _resolve_clone_path(resolved, rb.repo)
            if clone_path is None:
                raise click.ClickException(
                    f"No local clone for {rb.repo}. "
                    f"Set local path in project.yaml repos."
                )
            wt_path = worktree_path_for_session(clone_path, session_id)
            if wt_path.exists() and not resume_flag:
                raise click.ClickException(
                    f"Worktree path {wt_path} already exists. "
                    f"Use --resume or 'tripwire session cleanup {session_id}'."
                )
            if not wt_path.exists():
                from tripwire.core.git_helpers import branch_exists

                if branch_exists(clone_path, branch):
                    raise click.ClickException(
                        f"Branch '{branch}' already exists in {clone_path}. "
                        f"Use --resume to reuse it, or delete the branch first."
                    )
                base_ref = rb.base_branch or "HEAD"
                worktree_add(clone_path, wt_path, branch, base_ref)
            worktree_entries.append(
                WorktreeEntry(
                    repo=rb.repo,
                    clone_path=str(clone_path),
                    worktree_path=str(wt_path),
                    branch=branch,
                )
            )
            if primary_wt_path is None:
                primary_wt_path = wt_path

    if dry_run:
        click.echo(f"Dry run — would spawn session '{session_id}'")
        click.echo(f"  Branch: {branch}")
        for wt in worktree_entries:
            click.echo(f"  Worktree: {wt.worktree_path}")
        click.echo(f"  Max turns: {max_turns}")
        return

    if primary_wt_path is None:
        raise click.ClickException("No repos configured for this session")

    # Generate claude session ID
    claude_sid = (
        session.runtime_state.claude_session_id
        if resume_flag
        else str(_uuid_mod.uuid4())
    )

    # Log path
    if log_dir is None:
        log_dir = Path.home() / ".tripwire" / "logs"
    from tripwire.core.store import load_project as _lp

    try:
        proj = _lp(resolved)
        project_slug = proj.name.lower().replace(" ", "-")
    except Exception:
        project_slug = "unknown"
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
    log_file = log_dir / project_slug / f"{session_id}-{ts}.log"

    pid = _launch_claude(
        wt_path=primary_wt_path,
        plan_content=plan_content,
        session=session,
        project_dir=resolved,
        session_name=session.name,
        branch_type=branch_type,
        claude_session_id=claude_sid,
        max_turns=max_turns,
        log_path=log_file,
        project_slug=project_slug,
        resume=resume_flag,
    )

    now = datetime.now(tz=timezone.utc)
    session.status = "executing"
    session.runtime_state.worktrees = worktree_entries
    session.runtime_state.pid = pid
    session.runtime_state.claude_session_id = claude_sid
    session.runtime_state.started_at = now.isoformat()
    session.runtime_state.log_path = str(log_file)
    session.updated_at = now
    session.engagements.append(
        EngagementEntry(
            started_at=now,
            trigger="re_engagement" if resume_flag else "initial_launch",
        )
    )
    save_session(resolved, session)

    click.echo(f"Session '{session_id}' → executing")
    click.echo(f"  PID: {pid}")
    click.echo(f"  Branch: {branch}")
    click.echo(f"  Worktree: {primary_wt_path}")
    click.echo(f"  Log: {log_file}")
    click.echo(f"  Claude session: {claude_sid}")
    click.echo(f"\n  tail -f {log_file}")


@session_cmd.command("pause")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_pause_cmd(session_id: str, project_dir: Path) -> None:
    """SIGTERM the claude process, transition to paused."""
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

    pid = session.runtime_state.pid
    now = datetime.now(tz=timezone.utc)

    if pid and is_alive(pid):
        send_sigterm(pid)
        session.status = "paused"
        click.echo(f"Session '{session_id}' → paused (SIGTERM sent to PID {pid})")
    else:
        session.status = "failed"
        click.echo(f"Warning: PID {pid} not found — session '{session_id}' → failed")

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
    """Kill the process if running, transition to abandoned."""
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

    pid = session.runtime_state.pid
    if pid and session.status == "executing" and is_alive(pid):
        send_sigterm(pid)
        click.echo(f"Sent SIGTERM to PID {pid}")

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
        node = ConceptNode(
            id=proposal.id,
            type="model",
            name=proposal.name or proposal.id,
            status="active",
            body=proposal.body or "",
            related=proposal.related,
        )
        save_node(resolved, node, update_cache=False)
        click.echo(f"Created node {proposal.id}")
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
