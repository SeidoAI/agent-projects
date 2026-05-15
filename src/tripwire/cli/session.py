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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.artifacts import artifacts_list
from tripwire.core.git_helpers import (
    worktree_is_dirty,
    worktree_prune,
    worktree_remove,
)
from tripwire.core.jit_prompt_state import (
    record_bypass as _record_jit_prompt_bypass,
)
from tripwire.core.jit_prompt_state import (
    write_jit_prompt_ack_marker as _write_jit_prompt_ack_marker_core,
)
from tripwire.core.process_helpers import is_alive
from tripwire.core.session_check import (
    any_blocking_error,
    strict_check,
)
from tripwire.core.session_readiness import check_readiness
from tripwire.core.session_review_writer import (
    gather_pr_files as _gather_pr_files,
)
from tripwire.core.session_review_writer import (
    gather_pr_number as _gather_pr_number,
)
from tripwire.core.session_review_writer import (
    render_verified_md as _render_verified_md,  # noqa: F401  — re-exported for tests
)
from tripwire.core.session_review_writer import (
    write_review_json as _write_review_json,
)
from tripwire.core.session_review_writer import (
    write_verified_for_session as _write_verified_for_session,
)
from tripwire.core.session_store import list_sessions, load_session, save_session
from tripwire.core.task_checklist import parse_task_checklist
from tripwire.models.session import EngagementEntry

console = Console()


@dataclass
class SessionSummary:
    id: str
    name: str
    agent: str
    status: str
    issue_count: int
    repo_count: int
    cost_usd: float = 0.0
    over_budget: bool = False


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
    from tripwire.core.session_cost import compute_cost_from_log

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    summaries: list[SessionSummary] = []
    for s in sessions:
        # KUI-96 §E2 — cost column. Walk the persisted log if any; a
        # session that never spawned has no log_path → zero cost.
        log_path_str = s.runtime_state.log_path
        cost = 0.0
        if log_path_str:
            cost = compute_cost_from_log(Path(log_path_str).expanduser()).total_usd
        summaries.append(
            SessionSummary(
                id=s.id,
                name=s.name,
                agent=s.agent,
                status=s.status,
                issue_count=len(s.issues),
                repo_count=len(s.repos),
                cost_usd=cost,
                over_budget=s.runtime_state.cost_overrun_at is not None,
            )
        )

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
    table.add_column("cost", justify="right")
    for s in summaries:
        # v0.7.10 §3.A4 — flag budget-driven pauses next to status so a
        # human reading `session list` can tell apart manual pauses
        # from monitor-driven cost-overrun pauses.
        status_cell = f"{s.status} (over budget)" if s.over_budget else s.status
        table.add_row(
            s.id,
            s.name,
            s.agent,
            status_cell,
            str(s.issue_count),
            str(s.repo_count),
            f"${s.cost_usd:.4f}" if s.cost_usd else "—",
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
@click.option(
    "--full",
    "full",
    is_flag=True,
    default=False,
    help=(
        "Expand self-review.md and pm-response.yaml inline. Default "
        "shows a one-line presence summary so the output stays readable."
    ),
)
def session_show_cmd(
    session_id: str, project_dir: Path, output_format: str, full: bool
) -> None:
    """Print one session's YAML (text) or structured data (json).

    In `text` format, appends a brief review-artifact summary noting
    whether ``self-review.md`` and ``pm-response.yaml`` are committed
    to the session directory. ``--full`` expands them inline.
    """
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

    # v0.7.10 §3.A2 — show the resolved (provider, model, effort) so a
    # human can confirm the route before launch.
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.core.spawn_routing import UnknownTaskKindError, resolve_route

    spawn_defaults = load_resolved_spawn_config(resolved, session=session)
    task_kind = spawn_defaults.config.task_kind
    click.echo("Routing:")
    try:
        route = resolve_route(task_kind, resolved)
        click.echo(f"  task_kind: {route.task_kind}")
        click.echo(f"  provider: {route.provider}")
        click.echo(f"  model: {route.model}")
        click.echo(f"  effort: {route.effort}")
    except UnknownTaskKindError as exc:
        click.echo(f"  task_kind: {task_kind!r} — UNKNOWN ({exc})")

    from tripwire.core import paths as _paths

    sdir = _paths.session_dir(resolved, session_id)
    sr_path = sdir / "self-review.md"
    pr_path = sdir / "pm-response.yaml"

    click.echo("Review artifacts:")
    for label, path in (("self-review.md", sr_path), ("pm-response.yaml", pr_path)):
        if path.is_file():
            click.echo(f"  {label}: present")
        else:
            click.echo(f"  {label}: missing")

    if full:
        for label, path in (
            ("self-review.md", sr_path),
            ("pm-response.yaml", pr_path),
        ):
            if not path.is_file():
                continue
            click.echo()
            click.echo(f"--- {label} ---")
            click.echo(path.read_text(encoding="utf-8"))


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
    """Report launch-readiness + strict-check tripwires for a session.

    No state transition. Two parallel views are returned:

    - **Readiness items** (artifact presence, blocked-by, handoff.yaml)
      from :func:`tripwire.core.session_readiness.check_readiness`.
    - **Strict tripwires** (placeholder content, repos overlap,
      effort/model mismatch) from
      :func:`tripwire.core.session_check.strict_check` — the gates
      ``session spawn`` enforces with no bypass.

    Exit code is non-zero when *either* surface has an error.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        report = check_readiness(resolved, session_id, kind="check")
        strict_results = strict_check(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    items = report.items
    errors = [i for i in items if not i.passing and i.severity == "error"]
    strict_errors = [r for r in strict_results if r.severity == "error"]
    strict_warnings = [r for r in strict_results if r.severity == "warning"]
    launch_ready = not errors and not strict_errors

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "session_id": session_id,
                    "launch_ready": launch_ready,
                    "items": [asdict(i) for i in items],
                    "strict_checks": [asdict(r) for r in strict_results],
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
        if strict_results:
            click.echo("Strict checks (§A6):")
            for r in strict_results:
                mark = "✗" if r.severity == "error" else "!"
                click.echo(f"  {mark} {r.error_code}: {r.message}")
                if r.fix_hint:
                    click.echo(f"    → {r.fix_hint}")
            click.echo()
        if launch_ready:
            click.echo("Launch-ready.")
        else:
            blocking = len(errors) + len(strict_errors)
            warn_note = (
                f" ({len(strict_warnings)} warning(s) — non-blocking)"
                if strict_warnings
                else ""
            )
            click.echo(f"{blocking} must-fix. Not launch-ready.{warn_note}")
    if not launch_ready:
        raise click.exceptions.Exit(1)


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
@click.option(
    "--promote-issues",
    "promote_issues",
    is_flag=True,
    default=False,
    help=(
        "Before queueing, flip every session issue currently in "
        "`planned` status to `queued`. Leaves other statuses alone."
    ),
)
def session_queue_cmd(session_id: str, project_dir: Path, promote_issues: bool) -> None:
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

    if promote_issues:
        from tripwire.core.store import load_issue, save_issue

        promoted = 0
        for issue_key in session.issues:
            try:
                issue = load_issue(resolved, issue_key)
            except FileNotFoundError:
                click.echo(f"  ! issue {issue_key} not found — skipping")
                continue
            if str(issue.status) == "planned":
                issue.status = "queued"
                save_issue(resolved, issue)
                click.echo(f"  {issue_key}: planned → queued")
                promoted += 1
        if promoted == 0:
            click.echo("  (no issues at 'planned' to promote)")

    report = check_readiness(resolved, session_id, kind="queue")
    if not report.ready:
        for item in report.items:
            if not item.passing:
                click.echo(f"  ✗ {item.label}")
                if item.fix_hint:
                    click.echo(f"    → {item.fix_hint}")
        raise click.ClickException("Not ready to queue — fix errors above")

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    try:
        result = execute_transition(
            resolved,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="queued",
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc
    if not result.ok:
        raise click.ClickException(
            f"transition rejected: {result.message or result.reason}"
        )
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
@click.option(
    "--from-remote",
    "from_remote",
    type=str,
    default=None,
    help=(
        "Resume partial work from an existing remote branch. After "
        "creating the local worktree, ``git fetch origin <branch>`` "
        "and check out that branch into the worktree so the spawned "
        "agent inherits the in-progress code. Does not error on an "
        "existing remote branch the way a fresh spawn would."
    ),
)
def session_spawn_cmd(
    session_id: str,
    project_dir: Path,
    max_turns_override: int | None,
    log_dir: Path | None,
    dry_run: bool,
    resume_flag: bool,
    from_remote: str | None,
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
        raise click.ClickException(f"session '{session_id}' not found") from exc

    # --from-remote and --resume are mutually exclusive — they're two
    # different "the slot isn't clean" recoveries and combining them
    # would scramble the worktree state.
    if from_remote and resume_flag:
        raise click.ClickException(
            "--from-remote and --resume are mutually exclusive. "
            "--resume re-attaches to a paused/failed session's existing "
            "worktree; --from-remote hydrates a fresh worktree from a "
            "remote branch."
        )

    # Status gate. --resume is allowed from any non-terminal state.
    # Semantics by source state:
    #   paused / failed → re-attach to the runtime (the historic path)
    #   executing       → re-attach to the running runtime, or restart
    #                     it if the recorded pid is dead (e.g. host
    #                     reboot, OOM kill)
    #   in_review       → rare. The agent was conceptually waiting for
    #                     review feedback; resuming re-spawns the agent
    #                     with the review-feedback context loaded.
    # Terminal states fail loudly — resume after a session has reached
    # a terminal state is a backslide, not a resume.
    _TERMINAL_STATUSES_FOR_RESUME = ("verified", "completed", "abandoned")
    _PRE_SPAWN_STATUSES = ("planned", "queued")
    if resume_flag:
        if session.status == "verified":
            raise click.ClickException(
                f"--resume rejected: session '{session_id}' is 'verified'. "
                "Resuming a verified session is a backslide, not a resume — "
                "the verification artefact would be stale by definition. "
                "If real work remains, use 'tripwire session reopen' to "
                "move it back to 'paused' with an explicit audit reason."
            )
        if session.status in _TERMINAL_STATUSES_FOR_RESUME:
            raise click.ClickException(
                f"--resume rejected: session '{session_id}' is "
                f"'{session.status}' (terminal). Use 'tripwire session "
                "reopen' for completed sessions; abandoned sessions cannot "
                "be resumed."
            )
        if session.status in _PRE_SPAWN_STATUSES:
            raise click.ClickException(
                f"--resume rejected: session '{session_id}' is "
                f"'{session.status}' — it has never been spawned. Drop "
                "--resume to do the initial spawn."
            )
        # Any remaining state (executing, in_review, paused, failed) is
        # a valid resume source — fall through.
    else:
        if session.status != "queued":
            raise click.ClickException(
                f"session '{session_id}' is '{session.status}', must be 'queued' to spawn"
            )

    if not shutil.which("claude"):
        raise click.ClickException("claude CLI not found on PATH")

    # v0.7.9 §A6: strict pre-spawn check. No bypass — if anything fires,
    # the operator fixes it and re-runs. Skipped on --resume because the
    # session was already accepted on initial spawn; resuming should not
    # be re-blocked on artifact content that may have evolved during
    # execution.
    if not resume_flag:
        strict_results = strict_check(resolved, session_id)
        if any_blocking_error(strict_results):
            click.echo(
                f"session '{session_id}' fails {sum(1 for r in strict_results if r.severity == 'error')} "
                f"strict check(s); refusing to spawn:",
                err=True,
            )
            for r in strict_results:
                if r.severity == "error":
                    click.echo(f"  ✗ {r.error_code}: {r.message}", err=True)
                    if r.fix_hint:
                        click.echo(f"    → {r.fix_hint}", err=True)
            raise click.exceptions.Exit(1)

    # Resolve runtime from spawn config
    resolved_spawn = load_resolved_spawn_config(resolved, session=session)
    try:
        runtime = get_runtime(resolved_spawn.invocation.runtime)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Dry-run is pure: compute what prep WOULD produce (worktree paths,
    # runtime, max-turns) without running prep. Prep mutates the
    # filesystem (git worktree add + skill copy + CLAUDE.md render),
    # and until v0.7.3 dry-run ran prep first — leaving a worktree on
    # disk that blocked every subsequent real spawn with "worktree
    # already exists". Now dry-run just resolves symbolic paths.
    if dry_run:
        from tripwire.core.git_helpers import worktree_path_for_session

        click.echo(f"Dry run — would spawn session '{session_id}'")
        click.echo(f"  Runtime: {runtime.name}")
        for rb in session.repos:
            clone = _resolve_clone_path(resolved, rb.repo)
            if clone is None:
                click.echo(f"  Worktree: [unresolved: no local clone for {rb.repo}]")
                continue
            wt_path = worktree_path_for_session(clone, session.id)
            click.echo(f"  Worktree (would create): {wt_path}")
        click.echo(f"  Max turns: {resolved_spawn.config.max_turns}")
        return

    # Real spawn: now we're committed to mutating the filesystem.
    try:
        prepped = prep_run(
            session=session,
            project_dir=resolved,
            runtime=runtime,
            max_turns_override=max_turns_override,
            claude_session_id=(
                session.runtime_state.claude_session_id if resume_flag else None
            ),
            resume=resume_flag,
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    # --from-remote: prep_run created the worktree on the
    # handoff-derived branch; now fetch the partial-work branch from
    # origin and hard-reset the worktree onto it so the spawned agent
    # inherits the in-progress code.
    if from_remote:
        code_wt = prepped.code_worktree
        try:
            subprocess.run(
                ["git", "fetch", "origin", from_remote],
                cwd=str(code_wt),
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "checkout", "-B", from_remote, f"origin/{from_remote}"],
                cwd=str(code_wt),
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            raise click.ClickException(
                f"--from-remote: failed to hydrate worktree from "
                f"origin/{from_remote}: {stderr.strip() or exc}"
            ) from exc

    # Launch via the runtime
    start_result = runtime.start(prepped)

    # Persist runtime_state + new engagement BEFORE the status flip. The
    # executor reloads the session inside the transition lock so these
    # writes are observed when it flips status to `executing`.
    now = datetime.now(tz=timezone.utc)
    session.runtime_state.worktrees = start_result.worktrees
    session.runtime_state.claude_session_id = start_result.claude_session_id
    session.runtime_state.pid = start_result.pid
    session.runtime_state.started_at = start_result.started_at
    session.runtime_state.log_path = start_result.log_path
    session.runtime_state.last_spawn_resumed = resume_flag
    session.updated_at = now
    session.engagements.append(
        EngagementEntry(
            started_at=now,
            trigger="re_engagement" if resume_flag else "initial_launch",
        )
    )
    save_session(resolved, session)

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    try:
        result = execute_transition(
            resolved,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="executing",
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc
    if not result.ok:
        raise click.ClickException(
            f"transition rejected: {result.message or result.reason}"
        )

    click.echo(f"Session '{session_id}' → executing  (runtime: {runtime.name})")
    click.echo(f"  Branch: {prepped.worktrees[0].branch}")
    click.echo(f"  Code worktree: {prepped.code_worktree}")
    if start_result.pid:
        click.echo(f"  PID: {start_result.pid}")
    if start_result.log_path:
        click.echo(f"  Log: {start_result.log_path}")
        click.echo(f"\n  tripwire session attach {session_id}")
    click.echo(f"  Claude session: {start_result.claude_session_id}")


@session_cmd.command("batch-spawn")
@click.argument("session_ids", nargs=-1, required=True)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--prime/--no-prime",
    "prime",
    default=True,
    show_default=True,
    help=(
        "Send a no-op claude call with shared system content before "
        "the first spawn so subsequent spawns hit the warm prompt cache."
    ),
)
def session_batch_spawn_cmd(
    session_ids: tuple[str, ...],
    project_dir: Path,
    prime: bool,
) -> None:
    """Spawn N sessions in quick succession after priming the prompt cache.

    The shared system content for priming defaults to the project's
    ``CLAUDE.md``. Batches of one skip priming — the no-op call is not
    free.
    """
    from tripwire.core import batch_spawn as bs

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    report = bs.batch_spawn(
        resolved,
        list(session_ids),
        prime=prime,
        prime_runner=bs.default_prime_runner,
        spawn_runner=bs.default_spawn_runner,
    )
    if report.primed:
        click.echo("Cache primed: ✓")
    elif prime and len(session_ids) > 1:
        click.echo(
            "Cache priming was attempted but did not succeed; "
            "sessions will spawn without warm-cache benefit."
        )
    for sid in report.spawned:
        click.echo(f"Spawned: {sid}")
    for sid, reason in report.failed:
        click.echo(f"Failed:  {sid} ({reason})", err=True)
    if report.failed:
        raise click.exceptions.Exit(1)


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
    subprocess runtimes exec `tail -f <log>`; manual runtimes print
    the command to run."""
    import os

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime
    from tripwire.runtimes.base import AttachExec, AttachInstruction

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

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
    runtime = get_runtime(spawn.invocation.runtime)

    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    # For subprocess runtime, a dead pid means the agent already exited
    # (cleanly or otherwise). Surface that as 'failed' — pause doesn't
    # make sense once the process is gone.
    pid = session.runtime_state.pid
    if pid and not is_alive(pid):
        try:
            result = execute_transition(
                resolved,
                workflow_id="coding-session",
                instance_id=session_id,
                target_status="failed",
                flags={},
            )
        except TransitionError as exc:
            raise click.ClickException(str(exc)) from exc
        if not result.ok:
            raise click.ClickException(
                f"transition rejected: {result.message or result.reason}"
            )
        click.echo(f"Warning: PID {pid} not alive — session '{session_id}' → failed")
        return

    try:
        runtime.pause(session)
    except RuntimeError as exc:
        click.echo(f"Warning: {exc}", err=True)
        click.echo(
            f"Session '{session_id}' remains 'executing' — state matches reality"
        )
        return

    try:
        result = execute_transition(
            resolved,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="paused",
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc
    if not result.ok:
        raise click.ClickException(
            f"transition rejected: {result.message or result.reason}"
        )
    click.echo(f"Session '{session_id}' → paused")


# Session-status transitions are declared in `workflow.yaml` and
# executed by `tripwire.core.workflow.transitions.execute_transition`,
# which resolves the matching route, runs the gate (tripwires, JIT
# prompts, prompt-checks, artifact-existence), and atomically writes
# `session.status` plus a small fixed set of post-write housekeeping
# records (engagement close, audit, telemetry, ack reset).
#
# External side effects historically dispatched by the executor
# (sweep issues, rebase PT, kill runtime, flip draft PRs, etc.) now
# live as Layer-1/Layer-2 CLI wrappers and direct-mutation cli paths.


@session_cmd.command("transition")
@click.argument("session_id")
@click.argument("target_status")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_transition_cmd(
    session_id: str,
    target_status: str,
    project_dir: Path,
) -> None:
    """Transition a session's status via the workflow executor.

    Routes through ``tripwire.core.workflow.transitions.execute_transition``,
    which resolves the matching route in ``workflow.yaml`` from
    ``(current_status, target_status)``, runs the route's gate (tripwires
    listed in ``controls.tripwires``, JIT prompts, prompt-checks, consumed
    artifacts), atomically flips the status, then runs a small fixed set
    of best-effort post-write hooks (close active engagement on terminal
    transitions, append audit + telemetry records, reset acks if the
    route opts in).

    External side effects historically declared by ``route.side_effects``
    (sweep, PT-rebase, draft-PR flips, kill runtime, etc.) now live as
    Layer-1 CLI wrappers and direct-mutation cli paths; routes still
    document them informationally but the executor no longer orchestrates
    them. Per-route validation runs as the route's ``controls.tripwires``
    gate (the full project validator runs as ``tripwire validate``).
    """
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        result = execute_transition(
            resolved,
            session_id=session_id,
            target_status=target_status,
            flags={},
        )
    except TransitionError as exc:
        raise click.ClickException(str(exc)) from exc

    if not result.ok:
        raise click.ClickException(
            f"transition not reachable: {result.message or result.reason}"
        )

    click.echo(f"Session '{session_id}' → {target_status}")


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


@session_cmd.command("reopen")
@click.argument("session_id")
@click.option(
    "--reason",
    required=True,
    help="Why are you reopening? Recorded in the audit log.",
)
@click.option(
    "--reset-acks",
    "reset_acks",
    is_flag=True,
    default=False,
    help=(
        "Delete `.tripwire/acks/*-<session_id>-*.json` so the agent "
        "re-encounters every tripwire on resume. Use after substantial "
        "rework (PR closed + reopened, plan.md materially edited)."
    ),
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_reopen_cmd(
    session_id: str, reason: str, reset_acks: bool, project_dir: Path
) -> None:
    """Move a completed session back to ``paused`` for PR-fix iteration.

    Thin wrapper — see :func:`tripwire.core.session_reopen.reopen_session`
    for the side-effect contract. v0.13: the ready→draft PR flip moved
    to the Layer-1 ``tripwire session flip-drafts-draft`` command; we
    invoke it in-process here before calling the lifecycle helper so the
    end-to-end CLI behaviour is preserved.
    """
    from tripwire.core.session_reopen import reopen_session

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    # v0.13 in-process prep: flip recorded draft PRs ready → draft. The
    # daemon paths skip this; the CLI wrapper does it to preserve the
    # pre-v0.13 user-facing surface.
    try:
        session_for_prep = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc
    flipped: list[str] = []
    for wt in session_for_prep.runtime_state.worktrees:
        if not wt.draft_pr_url:
            continue
        try:
            subprocess.run(
                ["gh", "pr", "ready", wt.draft_pr_url, "--undo"],
                cwd=wt.worktree_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            flipped.append(wt.draft_pr_url)
        except (subprocess.SubprocessError, OSError, FileNotFoundError):
            pass

    try:
        result = reopen_session(resolved, session_id, reason, reset_acks=reset_acks)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    # Stamp the in-process flip outcomes onto the result for the CLI
    # summary (the helper no longer owns the gh ready-undo step).
    result.draft_prs_flipped = flipped

    click.echo(f"Session '{session_id}' reopened (→ paused). Reason: {reason}")
    if reset_acks:
        click.echo(f"Reset {result.acks_reset_count} tripwire ack(s).")
    click.echo(f"Spawn the resumed agent: tripwire session spawn {session_id} --resume")


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
@click.option(
    "--with-logs",
    "with_logs",
    is_flag=True,
    default=False,
    help="Also remove the session's log files from ~/.tripwire/logs/",
)
@click.option(
    "--preserve-work",
    "preserve_work",
    is_flag=True,
    default=False,
    help=(
        "Kill runtime processes and clear session locks, but KEEP "
        "worktrees, plan.md, and artifacts/ on disk. Use when you "
        "want to free up a stuck runtime without losing in-progress "
        "work. Default: full cleanup (worktrees + locks)."
    ),
)
def session_cleanup_cmd(
    session_id: str | None,
    project_dir: Path,
    clean_all: bool,
    force: bool,
    with_logs: bool,
    preserve_work: bool,
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

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    cleaned = 0
    for session in targets:
        # If the runtime still has a live process (claude subprocess, etc.),
        # tear it down before ripping the worktree out from under it.
        try:
            spawn = load_resolved_spawn_config(resolved, session=session)
            runtime = get_runtime(spawn.invocation.runtime)
            if runtime.status(session) == "running":
                runtime.abandon(session)
        except (ValueError, RuntimeError, FileNotFoundError):
            # Best-effort — unknown runtime / missing config shouldn't
            # block worktree cleanup.
            pass

        # --preserve-work: skip the worktree teardown + log-rm passes
        # below. Locks for this session still get cleared (the spawn
        # process is dead, so the lock is stale by definition).
        if preserve_work:
            locks_dir = resolved / ".tripwire" / "locks"
            removed_locks = 0
            if locks_dir.is_dir():
                # Match locks belonging to this session — both the
                # exact-id form ``<sid>.lock`` and the ``*-<sid>.lock``
                # form some workflow gates use.
                for lock in locks_dir.glob("*.lock"):
                    name = lock.stem
                    if name == session.id or name.endswith(f"-{session.id}"):
                        try:
                            lock.unlink()
                            removed_locks += 1
                        except OSError:
                            pass
            click.echo(
                f"  Preserved work for '{session.id}' "
                f"(runtime killed; {removed_locks} lock(s) cleared; "
                "worktrees + plan.md kept)"
            )
            continue

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

        # Orphan-worktree scan: filesystem worktrees matching
        # `*-wt-<session-id>` that weren't in runtime_state. Happens
        # when a spawn is interrupted before runtime_state gets
        # written, or when artefacts leaked from a pre-I5 dry-run.
        # Scan roots: every registered code-repo clone, plus
        # project_dir itself (v0.7.4 project-tracking worktrees live
        # as siblings of project_dir, not under any registered repo).
        recorded_paths = {
            Path(w.worktree_path).resolve() for w in session.runtime_state.worktrees
        }
        try:
            from tripwire.core.store import load_project

            proj = load_project(resolved)
        except Exception:
            proj = None
        scan_roots: list[Path] = []
        if proj and proj.repos:
            for _slug, repo_cfg in proj.repos.items():
                if repo_cfg.local:
                    clone = Path(repo_cfg.local).expanduser()
                    if clone.exists():
                        scan_roots.append(clone)
        if resolved.exists():
            scan_roots.append(resolved)

        suffix = f"-wt-{session.id}"
        for clone in scan_roots:
            for sibling in clone.parent.iterdir():
                if not sibling.is_dir() or not sibling.name.endswith(suffix):
                    continue
                if sibling.resolve() in recorded_paths:
                    continue  # already handled above
                if not force and worktree_is_dirty(sibling):
                    click.echo(
                        f"  Skipping orphan {sibling} — "
                        "uncommitted changes (use --force)"
                    )
                    continue
                worktree_remove(clone, sibling)
                clones_to_prune.add(str(clone))
                cleaned += 1
                click.echo(f"  Removed orphan: {sibling}")

        # Optionally drop the session's log files. Log files are named
        # <session_id>-<timestamp>.log under a shared {project_slug}
        # directory, so we glob-match rather than rm -rf the parent
        # (which would nuke other sessions' logs in the same project).
        if with_logs and session.runtime_state.log_path:
            log_parent = Path(session.runtime_state.log_path).expanduser().parent
            if log_parent.is_dir():
                removed = 0
                for log_file in log_parent.glob(f"{session.id}-*.log"):
                    log_file.unlink()
                    removed += 1
                if removed:
                    click.echo(f"  Removed {removed} log file(s) for '{session.id}'")

    for clone_str in clones_to_prune:
        worktree_prune(Path(clone_str))

    click.echo(f"Cleaned {cleaned} worktree(s)")


@session_cmd.command("scaffold")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing files instead of skipping them.",
)
@click.option(
    "--artifact",
    "artifact_name",
    default=None,
    help=(
        "Scaffold a specific artifact by file name "
        "(e.g. `verification-checklist.md`). Default: every planning-"
        "phase, PM-owned, required artifact from the manifest."
    ),
)
@click.option(
    "--no-handoff",
    is_flag=True,
    default=False,
    help=(
        "Skip writing handoff.yaml. Default behaviour: write handoff.yaml "
        "with a derived branch name if the file does not yet exist."
    ),
)
def session_scaffold_cmd(
    session_id: str,
    project_dir: Path,
    force: bool,
    artifact_name: str | None,
    no_handoff: bool,
) -> None:
    """Render session planning artifacts from their Jinja templates.

    Before this command existed, PMs copy-pasted
    ``verification-checklist.md`` from other sessions because there
    was no scaffolder. Readiness checks that artifact at queue time,
    so the missing step was a recurring onboarding papercut.

    Default: render every manifest entry where
    ``produced_at=="planning"``, ``owned_by=="pm"``, and
    ``required=True``. Pass ``--artifact <file>`` to scaffold a
    single entry. ``--force`` overwrites existing files.
    """
    from tripwire.core.manifest_loader import load_artifact_manifest

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    manifest, _findings = load_artifact_manifest(resolved)
    if manifest is None:
        raise click.ClickException(
            "No artifact manifest found at templates/artifacts/manifest.yaml"
        )

    if artifact_name:
        targets = [e for e in manifest.artifacts if e.file == artifact_name]
        if not targets:
            raise click.ClickException(
                f"artifact '{artifact_name}' not declared in manifest"
            )
    else:
        targets = [
            e
            for e in manifest.artifacts
            if e.produced_at == "planning" and e.owned_by == "pm" and e.required
        ]
        if not targets:
            click.echo("No planning-phase PM-owned required artifacts to scaffold.")
            return

    # Jinja loader pointed at the project's artifacts/templates dir.
    # init copies the packaged templates here at project-create time,
    # so scaffold respects whatever the user has customised locally.
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from tripwire.core import paths as _paths

    templates_root = resolved / "templates" / "artifacts"
    env = Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    session_root = _paths.session_dir(resolved, session_id)
    artifacts_dest_dir = _paths.session_artifacts_dir(resolved, session_id)
    session_root.mkdir(parents=True, exist_ok=True)
    artifacts_dest_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "session": session,
        "session_id": session_id,
        "session_name": session.name,
        "agent": session.agent,
        "issues": session.issues,
    }

    wrote = 0
    for entry in targets:
        dest = artifacts_dest_dir / entry.file
        if dest.exists() and not force:
            click.echo(f"  Skipping {entry.file} — exists (use --force to overwrite)")
            continue
        try:
            tpl = env.get_template(entry.template)
        except Exception as exc:
            raise click.ClickException(
                f"template {entry.template!r} not found under {templates_root}: {exc}"
            ) from exc
        rendered = tpl.render(**context)
        dest.write_text(rendered, encoding="utf-8")
        click.echo(f"  Wrote {_paths.SESSION_ARTIFACTS_SUBDIR}/{entry.file}")
        wrote += 1

    if wrote == 0 and not artifact_name:
        click.echo("  (nothing scaffolded — all targets already existed)")

    # Handoff.yaml — session state, not an artifact (lives outside the
    # manifest), but conceptually a planning-phase PM-owned file. PMs
    # should not have to hand-craft it; derive the branch from the
    # session's primary issue kind and write it here unless suppressed.
    if not no_handoff and not artifact_name:
        _scaffold_handoff(resolved, session, force)


def _scaffold_handoff(project_dir: Path, session, force: bool) -> None:
    """Write sessions/<id>/handoff.yaml with a derived branch name.

    Skips silently if the file already exists and `force` is False.
    Logs a warning (without failing) if branch derivation fails — the
    PM can still hand-write the file as a fallback.
    """
    import uuid as _uuid
    from datetime import datetime, timezone

    from tripwire.core.branch_naming import BranchNameError, derive_branch_name
    from tripwire.core.handoff_store import handoff_path, save_handoff
    from tripwire.core.store import load_issue
    from tripwire.models.handoff import SessionHandoff

    dest = handoff_path(project_dir, session.id)
    if dest.exists() and not force:
        click.echo("  Skipping handoff.yaml — exists (use --force to overwrite)")
        return

    # Pick the first issue's kind as the branch type. Fallback to "feat"
    # if no issues are bound or the first issue's kind isn't a valid
    # branch type for this project.
    primary_kind = "feat"
    if session.issues:
        try:
            first_issue = load_issue(project_dir, session.issues[0])
            if first_issue.kind:
                primary_kind = first_issue.kind
        except (FileNotFoundError, AttributeError):
            pass

    try:
        branch = derive_branch_name(session.id, primary_kind, project_dir=project_dir)
    except BranchNameError as exc:
        click.echo(f"  Skipping handoff.yaml — could not derive branch: {exc}")
        return

    handoff = SessionHandoff(
        uuid=_uuid.uuid4(),
        session_id=session.id,
        handoff_at=datetime.now(tz=timezone.utc),
        handed_off_by="pm",
        branch=branch,
    )
    save_handoff(project_dir, handoff)
    click.echo(f"  Wrote handoff.yaml (branch: {branch})")


@session_cmd.command("logs")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--tail",
    "tail_lines",
    type=int,
    default=50,
    show_default=True,
    help="Number of lines to show from the tail of the latest log file.",
)
@click.option(
    "--full",
    is_flag=True,
    default=False,
    help="Dump the entire latest log file instead of tailing.",
)
@click.option(
    "--list",
    "list_only",
    is_flag=True,
    default=False,
    help="List all log files for the session; don't dump contents.",
)
def session_logs_cmd(
    session_id: str,
    project_dir: Path,
    tail_lines: int,
    full: bool,
    list_only: bool,
) -> None:
    """Show log files for a session.

    Per-spawn logs accumulate under the shared
    ``~/.tripwire/logs/<project-slug>/`` directory as
    ``<session_id>-<timestamp>.log``. This subcommand surfaces them
    without requiring operators to grep the filesystem by hand.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    log_path_str = session.runtime_state.log_path
    if not log_path_str:
        raise click.ClickException(
            f"session '{session_id}' has no recorded log_path — "
            "the session may never have been spawned."
        )
    latest_log = Path(log_path_str).expanduser()
    log_dir = latest_log.parent
    if not log_dir.is_dir():
        raise click.ClickException(f"log directory does not exist: {log_dir}")

    matches = sorted(log_dir.glob(f"{session_id}-*.log"))
    if not matches and latest_log.is_file():
        matches = [latest_log]
    if not matches:
        raise click.ClickException(f"no log files found for session '{session_id}'")

    if list_only:
        for path in matches:
            st = path.stat()
            ts = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            click.echo(f"  {path.name}  {st.st_size:>10} bytes  {ts}")
        return

    latest = matches[-1]
    content = latest.read_text(encoding="utf-8", errors="replace")
    if full:
        click.echo(content, nl=False)
        return
    lines = content.splitlines()
    for line in lines[-tail_lines:]:
        click.echo(line)


@session_cmd.command("summary")
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
def session_summary_cmd(
    session_id: str,
    project_dir: Path,
    output_format: str,
) -> None:
    """Summarise the latest spawn attempt for a session.

    Parses the most recent stream-json log file into a readable
    shape: claude session uuid, exit subtype, tool-call count, token
    usage, and the final assistant text. Flags sessions that
    "stopped to ask" (clean exit whose final text contains a
    question).
    """
    import dataclasses
    import json as _json

    from tripwire.core.session_log_parser import format_text, parse

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    log_path_str = session.runtime_state.log_path
    if not log_path_str:
        raise click.ClickException(
            f"session '{session_id}' has no recorded log_path — "
            "the session may never have been spawned."
        )
    latest_log = Path(log_path_str).expanduser()
    log_dir = latest_log.parent
    matches = sorted(log_dir.glob(f"{session_id}-*.log")) if log_dir.is_dir() else []
    if not matches and latest_log.is_file():
        matches = [latest_log]
    if not matches:
        raise click.ClickException(f"no log files found for session '{session_id}'")

    summary = parse(matches[-1])
    if output_format == "json":
        payload = dataclasses.asdict(summary)
        payload["log_path"] = str(summary.log_path)
        click.echo(_json.dumps(payload, indent=2))
    else:
        click.echo(format_text(summary))


@session_cmd.command("cost")
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
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def session_cost_cmd(
    session_id: str,
    project_dir: Path,
    output_format: str,
) -> None:
    """Sum the per-token-category cost for a session's stream-json log.

    Pricing comes from ``data/anthropic_pricing.yaml`` (refresh
    manually). Sessions that have never spawned (no recorded
    ``runtime_state.log_path``) report a zero breakdown rather than
    erroring — useful for the ``Cost`` column in ``session list``.
    """
    from tripwire.core.session_cost import compute_session_cost

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        breakdown = compute_session_cost(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    if output_format == "json":
        payload = {"session_id": session_id, **breakdown.as_dict()}
        click.echo(json.dumps(payload, indent=2))
        return

    table = Table(title=f"Cost: {session_id}", show_header=True)
    table.add_column("category")
    table.add_column("tokens", justify="right")
    table.add_column("usd", justify="right")
    rows: list[tuple[str, int, float]] = [
        ("input", breakdown.input_tokens, breakdown.input_usd),
        ("output", breakdown.output_tokens, breakdown.output_usd),
        ("cache_read", breakdown.cache_read_tokens, breakdown.cache_read_usd),
        ("cache_write", breakdown.cache_write_tokens, breakdown.cache_write_usd),
    ]
    for label, tokens, usd in rows:
        table.add_row(label, f"{tokens:,}", f"${usd:.4f}")
    table.add_row("[bold]total[/bold]", "", f"[bold]${breakdown.total_usd:.4f}[/bold]")
    console.print(table)
    if breakdown.models_used:
        console.print(f"[dim]models seen: {', '.join(breakdown.models_used)}[/dim]")


@session_cmd.command("analyze-routing")
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
def session_analyze_routing_cmd(project_dir: Path, output_format: str) -> None:
    """Aggregate ``.routing_telemetry.jsonl`` rows by route.

    Thin wrapper — see :func:`tripwire.core.routing_analysis.aggregate_routes`
    for the per-route metrics computed.
    """
    from tripwire.core.routing_analysis import aggregate_routes, render_routing_table
    from tripwire.core.routing_telemetry import read_telemetry

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    rows = read_telemetry(resolved)
    routes_payload = aggregate_routes(rows)

    if output_format == "json":
        click.echo(
            json.dumps(
                {"total_sessions": len(rows), "routes": routes_payload}, indent=2
            )
        )
        return

    render_routing_table(routes_payload, console)


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
# `tripwire session log` — per-session JIT prompt fire log (KUI-99)
# ----------------------------------------------------------------------------


@session_cmd.command("log")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--web",
    is_flag=True,
    default=False,
    help="Print a deep-link to the UI JIT Prompt Log filtered to this session.",
)
@click.option(
    "--reveal",
    is_flag=True,
    default=False,
    help="Reveal each fire's prompt body (PM-only).",
)
def session_log_cmd(
    session_id: str, project_dir: Path, web: bool, reveal: bool
) -> None:
    """Show all JIT prompt fires for a session, with timestamps and acks.

    Thin wrapper — see :func:`tripwire.core.session_log.enumerate_fires`.
    """
    from tripwire.cli.jit_prompts import _is_pm
    from tripwire.core.session_log import enumerate_fires

    resolved = project_dir.expanduser().resolve()

    if web:
        click.echo(
            f"JIT Prompt Log: http://localhost:8000/jit-prompts?session_id={session_id}"
        )

    entries = list(enumerate_fires(resolved, session_id))
    if not entries:
        click.echo(f"No JIT prompt fires for session {session_id!r}.")
        return

    pm_mode = _is_pm()
    for entry in entries:
        if entry.unreadable:
            name = entry.source_path.name if entry.source_path else "?"
            click.echo(f"  <unreadable: {name}>")
            continue
        flag = " ESCALATED" if entry.escalated else ""
        click.echo(
            f"  {entry.fired_at}  {entry.jit_prompt_id}  on={entry.event}  "
            f"status={entry.ack_status}{entry.ack_detail}{flag}"
        )
        if reveal and pm_mode:
            body = entry.prompt_revealed or "(prompt not persisted)"
            indented = "\n".join("    " + line for line in body.splitlines())
            click.echo(indented)


# ----------------------------------------------------------------------------
# `tripwire session complete` — close-out orchestration
# ----------------------------------------------------------------------------


@session_cmd.command("complete")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option("--dry-run", is_flag=True, default=False)
@click.option(
    "--ack",
    is_flag=True,
    default=False,
    help=(
        "Write the JIT prompt ack marker rather than running the close-out. "
        "Requires `--fix-commit` (≥1) OR `--declared-no-findings`."
    ),
)
@click.option(
    "--fix-commit",
    "fix_commits",
    multiple=True,
    help="Commit SHA addressing a JIT prompt finding (use multiple times).",
)
@click.option(
    "--declared-no-findings",
    is_flag=True,
    default=False,
    help="Acknowledge the JIT prompt with an explicit no-findings declaration.",
)
@click.option(
    "--jit-prompt-id",
    "jit_prompt_id",
    type=str,
    default="self-review",
    show_default=True,
    help=(
        "Which JIT prompt to ack. Defaults to `self-review`. Use the id of "
        "any v0.9 deviation JIT prompt fired on "
        "session.complete (phase-transition, followups-not-filed, "
        "stopped-to-ask, write-count, cost-ceiling)."
    ),
)
@click.option(
    "--no-jit-prompts",
    is_flag=True,
    default=False,
    help=(
        "Bypass JIT prompt firing (still runs close-out gates). Logs an "
        "audit entry to `.tripwire/audit/jit_prompt_bypass.log`."
    ),
)
@click.option(
    "--web",
    is_flag=True,
    default=False,
    help="After complete, print a deep-link to the UI JIT Prompt Log.",
)
def session_complete_cmd(
    session_id: str,
    project_dir: Path,
    dry_run: bool,
    ack: bool,
    fix_commits: tuple[str, ...],
    declared_no_findings: bool,
    jit_prompt_id: str,
    no_jit_prompts: bool,
    web: bool,
) -> None:
    """Complete a session: verify PRs merged, close issues, cleanup.

    The session.complete lifecycle event fires the JIT prompt registry
    BEFORE the close-out gates run. On a first call (no marker), the
    self-review JIT prompt returns its prompt on stdout and the command
    exits 1. The agent acks via `--ack --fix-commit <sha>` (≥1) OR
    `--ack --declared-no-findings`, and then re-runs without `--ack`
    to invoke the close-out gates as in v0.7.x.

    `--no-jit-prompts` bypasses the JIT prompt fire entirely (audit entry
    written). `jit_prompts.enabled: false` in project.yaml disables them
    project-wide.

    Close-out gates are unchanged from v0.7.9 §A4: PR merged, issue
    artifacts present, review.json exit_code ≤ 1. There are no bypass
    flags for the gates themselves.
    """
    from tripwire._internal.jit_prompts import fire_jit_prompt_event
    from tripwire.core.session_complete import (
        CompleteError,
        complete_session,
    )

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    if ack:
        _write_jit_prompt_ack(
            project_dir=resolved,
            session_id=session_id,
            jit_prompt_id=jit_prompt_id,
            fix_commits=list(fix_commits),
            declared_no_findings=declared_no_findings,
        )
        click.echo(
            f"JIT prompt {jit_prompt_id!r} acknowledged for session {session_id}. "
            f"Re-run without --ack to invoke close-out."
        )
        return

    if no_jit_prompts:
        _record_jit_prompt_bypass(
            project_dir=resolved,
            session_id=session_id,
            event="session.complete",
        )
    else:
        fire = fire_jit_prompt_event(
            project_dir=resolved,
            event="session.complete",
            session_id=session_id,
        )
        if fire.blocked:
            for prompt in fire.prompts:
                click.echo(prompt)
            raise SystemExit(1)

    # v0.13: pre-flight side-effects that used to run inline inside
    # ``complete_session()`` — flip drafts to ready, sweep member issues
    # forward. The agent procedure now runs ``tripwire session
    # prepare-for-completion`` as a separate step; do the same work
    # in-process here so the ``tripwire session complete`` CLI behaviour
    # is preserved end-to-end. Skipped in dry-run (no mutations).
    sweep_closed: list[str] = []
    if not dry_run:
        try:
            session_for_prep = load_session(resolved, session_id)
        except FileNotFoundError as exc:
            raise click.ClickException(f"session '{session_id}' not found") from exc
        from tripwire.core.session_complete import _flip_drafts_to_ready
        from tripwire.core.status_contract import sweep_issues

        _flip_drafts_to_ready(session_for_prep)
        sweep_closed = sweep_issues(resolved, session_for_prep, "completed")

    try:
        result = complete_session(resolved, session_id, dry_run=dry_run)
    except CompleteError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(f"Dry run: session {session_id} can be completed.")
        if result.node_diffs:
            click.echo(f"  Node diffs to review: {len(result.node_diffs)}")
        return

    # Stamp the sweep + worktree-removal outcomes onto the result for
    # the CLI summary (these moved out of complete_session()).
    result.issues_closed = sweep_closed
    try:
        session_after = load_session(resolved, session_id)
    except FileNotFoundError:
        session_after = None
    if session_after is not None and session_after.runtime_state:
        from tripwire.core.git_helpers import worktree_remove

        for wt in session_after.runtime_state.worktrees:
            try:
                worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
                result.worktrees_removed.append(wt.worktree_path)
            except (subprocess.SubprocessError, OSError):
                pass

    click.echo(f"Session {session_id} → completed")
    for iss in result.issues_closed:
        click.echo(f"  closed: {iss}")
    for wt in result.worktrees_removed:
        click.echo(f"  removed worktree: {wt}")

    if web:
        click.echo(
            f"  JIT Prompt Log: http://localhost:8000/jit-prompts?session_id={session_id}"
        )


def _write_jit_prompt_ack(
    *,
    project_dir: Path,
    session_id: str,
    jit_prompt_id: str,
    fix_commits: list[str],
    declared_no_findings: bool,
) -> None:
    """Thin click wrapper — see ``core.jit_prompt_state.write_jit_prompt_ack_marker``."""
    try:
        _write_jit_prompt_ack_marker_core(
            project_dir=project_dir,
            session_id=session_id,
            jit_prompt_id=jit_prompt_id,
            fix_commits=fix_commits,
            declared_no_findings=declared_no_findings,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


# ----------------------------------------------------------------------------
# `tripwire session review` — PR diff vs. issue specs
# ----------------------------------------------------------------------------


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


# ----------------------------------------------------------------------------
# `tripwire session prepare-review` — scaffold pr-review.yaml from
# member-issue ACs. Carries the PM's substantive review record:
# authored during `/pm-session-review`; validator gates the
# transition to `verified` on its content (`pr_review/*` rules).
# ----------------------------------------------------------------------------


@session_cmd.command("prepare-review")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite an existing pr-review.yaml.",
)
def session_prepare_review_cmd(
    session_id: str,
    project_dir: Path,
    force: bool,
) -> None:
    """Scaffold `sessions/<sid>/pr-review.yaml` from the session's
    member-issue ACs.

    PM-review enforcement: the PM runs this as the first step of
    `/pm-session-review`, then fills in `verified_by` evidence,
    four-lens findings, external-reviewer signals, and threshold-finding
    decisions before transitioning the session to `verified`. The
    validator's `pr_review/*` rules gate that transition on the file's
    substance.

    Refuses to overwrite an existing pr-review.yaml unless `--force` is
    set, so a partially-filled review isn't blown away.
    """
    import re as _re
    from datetime import datetime, timezone

    from tripwire.core.store import load_issue

    def parse_acceptance_criteria_from_body(body: str | None) -> list[str]:
        """Pull the `## Acceptance criteria` checklist out of an issue
        body. Returns the raw bullet text minus the `[ ]` / `[x]` prefix.

        Tolerant: matches `## Acceptance criteria` (case-insensitive) and
        accepts any subsequent indentation level for bullets. Stops at the
        next `##` heading.
        """
        if not body:
            return []
        lines = body.splitlines()
        in_section = False
        items: list[str] = []
        for line in lines:
            stripped = line.strip()
            if _re.match(r"^##\s+acceptance criteria\b", stripped, _re.IGNORECASE):
                in_section = True
                continue
            if in_section and stripped.startswith("##"):
                break
            if not in_section:
                continue
            m = _re.match(r"^[-*]\s*(?:\[[ xX]\]\s*)?(.+)$", stripped)
            if m:
                items.append(m.group(1).strip())
        return items

    from tripwire.core import paths as _paths

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session '{session_id}' not found") from exc

    sdir = _paths.session_dir(resolved, session_id)
    sdir.mkdir(parents=True, exist_ok=True)
    target = sdir / "pr-review.yaml"
    if target.exists() and not force:
        raise click.ClickException(
            f"{target.relative_to(resolved)} already exists; pass --force to overwrite."
        )

    issues_block: list[dict] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(resolved, issue_key)
        except FileNotFoundError:
            continue
        acs = parse_acceptance_criteria_from_body(issue.body)
        issues_block.append(
            {
                "key": issue_key,
                "acs": [
                    {
                        "text": ac,
                        "verified_by": [],
                        "decision": "verified",
                    }
                    for ac in (acs or ["<no acceptance criteria found in issue body>"])
                ],
            }
        )

    skeleton = {
        "read_at": datetime.now(tz=timezone.utc).isoformat(),
        "read_by": "pm",
        "pr": {"code": None, "pt": None},
        "issues": issues_block,
        "four_lens": {
            "ac_met_but_not_really": {"findings": []},
            "unilateral_decisions": {"findings": []},
            "skipped_workflow": {"findings": []},
            "quality_degradation": {"findings": []},
        },
        "external_reviews": {},
        "threshold_findings": {
            "threshold": 65,
            "count_above": 0,
            "count_addressed": 0,
            "unaddressed": [],
        },
        "verdict": "approved",
    }

    import yaml as _yaml

    target.write_text(
        "# PM-review record. Fill `verified_by` arrays with concrete\n"
        "# file:line citations or short evidence strings before transitioning\n"
        "# the session to `verified`. The validator's pr_review/* rules\n"
        "# block transition on placeholders or missing evidence.\n\n"
        + _yaml.safe_dump(skeleton, sort_keys=False),
        encoding="utf-8",
    )
    click.echo(f"Scaffolded {target.relative_to(resolved)}")
    click.echo(
        f"  {len(issues_block)} issue(s), "
        f"{sum(len(i['acs']) for i in issues_block)} AC(s)"
    )
    click.echo("Next: fill `verified_by` arrays + four_lens findings, then run")
    click.echo(f"  tripwire session transition {session_id} verified")


# ----------------------------------------------------------------------------
# `tripwire session review-artifacts` — render self-review.md
# + pm-response.yaml side-by-side, mark unaddressed self-review items.
# Sibling to `session review`; see decisions.md for the naming rationale.
# ----------------------------------------------------------------------------


@session_cmd.command("review-artifacts")
@click.argument("session_id")
@click.option("--project-dir", type=click.Path(path_type=Path), default=".")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["human", "json"]),
    default="human",
    show_default=True,
    help="Output format. `human` is a terminal-friendly side-by-side view.",
)
def session_review_artifacts_cmd(
    session_id: str, project_dir: Path, output_format: str
) -> None:
    """Render sessions/<sid>/self-review.md + pm-response.yaml side by side.

    Marks self-review items that have no matching pm-response entry as
    unaddressed. Tolerates missing files — emits a clear hint when one
    side is absent rather than erroring out.
    """
    import json as _json
    from dataclasses import asdict

    from tripwire.core.session_review_artifacts import build_report

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    # load_session validates the session exists; we don't otherwise use it.
    load_session(resolved, session_id)

    report = build_report(resolved, session_id)

    if output_format == "json":
        click.echo(_json.dumps(asdict(report), indent=2, default=str))
        return

    # human format
    click.echo(f"Session review-artifacts: {session_id}")
    click.echo()

    if not report.self_review_present:
        click.echo("self-review.md missing — agent has not authored one yet.")
    if not report.pm_response_present:
        click.echo("pm-response.yaml missing — PM has not responded yet.")

    if report.self_review_present and not report.pairs:
        click.echo("self-review.md has no items under any `## Lens N:` heading.")

    for pair in report.pairs:
        click.echo(f"  Lens {pair.self_review_lens}: {pair.self_review_text}")
        if pair.pm_response is None:
            click.echo("    PM: (unaddressed)")
            continue
        decision = pair.pm_response.decision or "(no decision)"
        line = f"    PM [{decision}]"
        extras: list[str] = []
        if pair.pm_response.follow_up:
            extras.append(f"follow_up={pair.pm_response.follow_up}")
        if pair.pm_response.fix_commit:
            extras.append(f"fix_commit={pair.pm_response.fix_commit}")
        if extras:
            line += " (" + ", ".join(extras) + ")"
        click.echo(line)
        if pair.pm_response.note:
            click.echo(f"      → {pair.pm_response.note}")

    if report.unaddressed:
        click.echo()
        click.echo(
            f"{len(report.unaddressed)} unaddressed self-review item(s); "
            "PM should add quote_excerpt entries to pm-response.yaml."
        )


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


# ----------------------------------------------------------------------
# v0.13 Layer-1 wrappers around side-effect handler bodies.
# ----------------------------------------------------------------------
#
# These commands let an operator replay one side-effect at a time
# without driving a transition. The workflow executor still owns
# orchestration; each command here is a thin click wrapper.


@session_cmd.command("kill-runtime")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_kill_runtime_cmd(session_id: str, project_dir: Path) -> None:
    """SIGTERM the session's recorded runtime pid. Best-effort.

    Reads ``session.runtime_state.pid`` and sends ``SIGTERM``. A
    missing pid is a clean no-op; ``ESRCH`` (pid already dead) is
    swallowed; any other OS error surfaces as a click error so the
    operator can investigate.
    """
    import os
    import signal

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    pid = session.runtime_state.pid if session.runtime_state else None
    if not pid:
        click.echo(
            f"session {session_id}: no runtime pid recorded; skipping",
            err=True,
        )
        return
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"sent SIGTERM to pid {pid} (session {session_id})")
    except ProcessLookupError:
        click.echo(f"pid {pid} already dead; skipping", err=True)
    except OSError as exc:
        raise click.ClickException(f"failed to signal pid {pid}: {exc}") from exc


@session_cmd.command("close-prs")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_close_prs_cmd(session_id: str, project_dir: Path) -> None:
    """Close any open PR across the session's recorded worktrees.

    Iterates ``session.runtime_state.worktrees`` and calls the
    canonical :func:`tripwire.core.session_abandon._close_pr_for_branch`
    helper for each. Skips merged PRs. Best-effort — per-worktree
    failures are reported but never abort the loop.
    """
    from tripwire.core.session_abandon import _close_pr_for_branch

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    closed: list[int] = []
    errors: list[str] = []
    for wt in session.runtime_state.worktrees:
        if not wt.branch:
            continue
        verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
        if verdict.closed_pr is not None and verdict.closed_pr > 0:
            closed.append(verdict.closed_pr)
        if verdict.error:
            errors.append(verdict.error)

    for pr in closed:
        click.echo(f"closed PR #{pr}")
    for err in errors:
        click.echo(f"warning: {err}", err=True)
    if not closed and not errors:
        click.echo(f"session {session_id}: no open PRs to close")


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
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

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

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    _flip_drafts_to_ready(session)
    click.echo(f"flipped drafts to ready for session {session_id}")


@session_cmd.command("flip-drafts-draft")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_flip_drafts_draft_cmd(session_id: str, project_dir: Path) -> None:
    """Flip every ready PR on the session's worktrees back to draft.

    Mirrors the ``flip_drafts_to_draft`` side-effect: for each worktree
    with a recorded ``draft_pr_url``, run ``gh pr ready <url> --undo``.
    Best-effort — ``gh`` errors are swallowed (the operator can re-run
    or inspect ``gh`` output directly).
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    flipped: list[str] = []
    for wt in session.runtime_state.worktrees:
        if not wt.draft_pr_url:
            continue
        try:
            subprocess.run(
                ["gh", "pr", "ready", wt.draft_pr_url, "--undo"],
                check=False,
                capture_output=True,
                text=True,
            )
            flipped.append(wt.draft_pr_url)
        except OSError:
            continue

    for url in flipped:
        click.echo(f"flipped to draft: {url}")
    if not flipped:
        click.echo(f"session {session_id}: no draft URLs to flip")


@session_cmd.command("normalise-branch")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_normalise_branch_cmd(session_id: str, project_dir: Path) -> None:
    """Reset squash-merged worktree branches to ``origin/main``.

    For each recorded worktree, asks ``gh`` whether the PR for the
    branch was merged. If merged AND the local branch still carries
    commits not present on ``origin/main`` (the canonical fingerprint
    of a squash-merge — the original commits stay behind on the
    feature branch), runs ``git reset --hard origin/main`` in the
    worktree. Idempotent: a worktree whose branch is already at
    ``origin/main`` is left alone; an unmerged PR is left alone.

    Skips worktrees whose path is missing on disk (e.g. already
    cleaned up by ``session complete``) and reports them as warnings.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees", err=True)
        return

    reset: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []
    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        if not wt_path.is_dir():
            skipped.append(f"{wt_path}: worktree missing")
            continue

        # Look up the PR for this branch — gh may return nothing if no
        # PR was ever opened; we treat that as "nothing to normalise".
        try:
            listing = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    wt.branch,
                    "--state",
                    "merged",
                    "--json",
                    "number,mergedAt,mergeCommit",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=str(wt_path),
            )
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"gh pr list failed for {wt.branch}: {exc}")
            continue

        if listing.returncode != 0:
            errors.append(
                f"gh pr list for {wt.branch} exit={listing.returncode}: "
                f"{(listing.stderr or '').strip()}"
            )
            continue

        try:
            prs = json.loads(listing.stdout or "[]")
        except json.JSONDecodeError as exc:
            errors.append(f"gh pr list invalid JSON for {wt.branch}: {exc}")
            continue

        if not prs or not prs[0].get("mergedAt"):
            skipped.append(f"{wt.branch}: PR not merged")
            continue

        # Squash detection — does the local branch have commits absent
        # from origin/main? `git rev-list --count origin/main..HEAD`
        # answers that in one shot.
        try:
            ahead = subprocess.run(
                ["git", "-C", str(wt_path), "rev-list", "--count", "origin/main..HEAD"],
                check=False,
                capture_output=True,
                text=True,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            errors.append(f"git rev-list failed for {wt_path}: {exc}")
            continue
        if ahead.returncode != 0:
            errors.append(
                f"git rev-list for {wt_path} exit={ahead.returncode}: "
                f"{(ahead.stderr or '').strip()}"
            )
            continue
        try:
            count = int((ahead.stdout or "0").strip())
        except ValueError:
            errors.append(f"git rev-list returned non-int for {wt_path}")
            continue
        if count == 0:
            skipped.append(f"{wt.branch}: already at origin/main")
            continue

        try:
            subprocess.run(
                ["git", "-C", str(wt_path), "reset", "--hard", "origin/main"],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            errors.append(
                f"git reset --hard origin/main for {wt_path} failed: "
                f"{(exc.stderr or '').strip()}"
            )
            continue
        reset.append(wt.worktree_path)

    for path in reset:
        click.echo(f"reset to origin/main: {path}")
    for entry in skipped:
        click.echo(f"skipped: {entry}", err=True)
    for err in errors:
        click.echo(f"warning: {err}", err=True)


@session_cmd.command("followup-stub")
@click.argument("session_id")
@click.option(
    "--reason",
    default="",
    help="Reopen reason recorded in the PM follow-up section.",
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_followup_stub_cmd(session_id: str, reason: str, project_dir: Path) -> None:
    """Append the canonical PM follow-up stub to the session's plan.md.

    Resolves the plan path via :func:`paths.session_plan_path` (the
    canonical ``sessions/<sid>/artifacts/plan.md`` location). Idempotent
    — re-running once the stub is present is a clean no-op.
    """
    from tripwire.core import paths as _paths

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    plan_path = _paths.session_plan_path(resolved, session_id)
    if not plan_path.is_file():
        click.echo(
            f"session {session_id}: plan.md not found at {plan_path}",
            err=True,
        )
        return
    text = plan_path.read_text(encoding="utf-8")
    if "## PM follow-up" in text:
        click.echo(f"session {session_id}: PM follow-up section already present")
        return
    reason_str = reason or "<reason omitted>"
    appended = (
        f"\n\n## PM follow-up\n\n"
        f"Session reopened by PM. Reason: {reason_str}.\n\n"
        f"Re-engage the agent via `tripwire session spawn {session_id} --resume`.\n"
    )
    plan_path.write_text(text + appended, encoding="utf-8")
    click.echo(f"appended PM follow-up stub to {plan_path}")


# ----------------------------------------------------------------------
# v0.13 Layer-2 chained commands.
# ----------------------------------------------------------------------
#
# These compose the Layer-1 wrappers above into the "common combos" an
# agent runs before a workflow transition. Each chain is idempotent and
# fails loud + actionable when a step blocks the transition.


@session_cmd.command("prepare-for-completion")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_prepare_for_completion_cmd(session_id: str, project_dir: Path) -> None:
    """Pre-flight a session for the ``coding-session → completed`` transition.

    Runs three checks in order, each gated on the previous passing:

    1. ``tripwire validate --select <sid>`` — the project must be clean
       under the session's selector. Any error fails loud.
    2. ``tripwire session flip-drafts-ready <sid>`` — flip every draft
       PR on the session's worktrees to ready-for-review. Idempotent.
    3. ``gh pr view --json state,mergeStateStatus`` per worktree. If
       any PR is ``BLOCKED`` or ``BEHIND``, exit 1 with the PR number
       + reason; ``MERGEABLE`` or already ``MERGED`` PRs are clean.

    Exits 0 only when all three steps pass. Idempotent — safe to re-run
    after the agent has fixed whatever each loud failure pointed at.
    """
    from tripwire.cli.validate import _filter_report_by_selector
    from tripwire.core.session_complete import _flip_drafts_to_ready
    from tripwire.core.validator import validate_project

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    # Step 1: validate, filtered by selector
    report = validate_project(resolved, strict=True, heuristic_mode="surface")
    _filter_report_by_selector(report, resolved, session_id)
    if report.errors:
        click.echo(
            f"validate failed for session {session_id}: {len(report.errors)} error(s)",
            err=True,
        )
        for err in report.errors:
            location = err.file or ""
            if err.field:
                location = f"{location}:{err.field}" if location else err.field
            click.echo(f"  [{err.code}] {location} — {err.message}", err=True)
        raise click.ClickException(f"validate gate blocked completion for {session_id}")
    click.echo(f"validate clean for session {session_id}")

    # Step 2: flip drafts to ready
    _flip_drafts_to_ready(session)
    click.echo(f"flipped drafts to ready for session {session_id}")

    # Step 3: per-PR merge readiness via gh pr view
    if session.runtime_state is None or not session.runtime_state.worktrees:
        click.echo(f"session {session_id}: no recorded worktrees")
        return

    blockers: list[str] = []
    checked: list[str] = []
    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        if not wt_path.is_dir():
            # Worktree gone — can't ask gh from inside it. Skip with a
            # warning so the agent sees what we couldn't check.
            click.echo(
                f"warning: worktree {wt.worktree_path} missing; "
                f"cannot check PR for branch {wt.branch}",
                err=True,
            )
            continue
        try:
            view = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    "--json",
                    "number,state,mergeStateStatus",
                ],
                cwd=str(wt_path),
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            blockers.append(f"gh pr view failed for {wt.branch}: {exc}")
            continue
        if view.returncode != 0:
            blockers.append(
                f"gh pr view for {wt.branch} exit={view.returncode}: "
                f"{(view.stderr or '').strip()}"
            )
            continue
        try:
            data = json.loads(view.stdout or "{}")
        except json.JSONDecodeError as exc:
            blockers.append(f"gh pr view invalid JSON for {wt.branch}: {exc}")
            continue
        num = data.get("number")
        state = (data.get("state") or "").upper()
        merge_status = (data.get("mergeStateStatus") or "").upper()
        label = f"PR #{num}" if num else f"PR for {wt.branch}"
        checked.append(f"{label}: state={state} merge={merge_status}")
        if state == "MERGED":
            continue
        if merge_status in {"BLOCKED", "BEHIND"}:
            blockers.append(f"{label}: mergeStateStatus={merge_status}")
            continue
        # CLEAN / UNSTABLE / HAS_HOOKS / MERGEABLE / UNKNOWN all pass —
        # only the explicit BLOCKED/BEHIND signals are actionable.

    for line in checked:
        click.echo(line)

    if blockers:
        click.echo(
            f"session {session_id}: {len(blockers)} PR(s) not mergeable", err=True
        )
        for b in blockers:
            click.echo(f"  {b}", err=True)
        raise click.ClickException(f"PRs blocking completion for session {session_id}")

    click.echo(f"session {session_id}: ready for completion")


@session_cmd.command("prepare-for-abandon")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_prepare_for_abandon_cmd(session_id: str, project_dir: Path) -> None:
    """Tear down a session's live state before the abandon transition.

    Runs three Layer-1 wrappers back to back, each best-effort:

    1. ``kill-runtime`` — SIGTERM the recorded runtime pid (no-op if none).
    2. ``close-prs`` — close any open PRs on the session's worktrees.
    3. ``remove-worktrees`` — delete the worktree directories.

    Per-step failures are collected, not raised — we always make a best
    effort to complete every step. Exit 0 if everything succeeded or
    was a no-op; exit 1 with a per-step summary if any step had a hard
    failure so the operator knows what to clean up manually.
    """
    from tripwire.core.session_abandon import _close_pr_for_branch

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    failures: list[str] = []

    # Step 1: kill-runtime — same logic as session_kill_runtime_cmd, inlined
    # so we can collect errors rather than re-raise.
    import os
    import signal

    pid = session.runtime_state.pid if session.runtime_state else None
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            click.echo(f"sent SIGTERM to pid {pid}")
        except ProcessLookupError:
            click.echo(f"pid {pid} already dead; skipping", err=True)
        except OSError as exc:
            failures.append(f"kill-runtime: failed to signal pid {pid}: {exc}")
    else:
        click.echo(f"session {session_id}: no runtime pid recorded; skipping")

    # Step 2: close-prs — same as session_close_prs_cmd.
    if session.runtime_state and session.runtime_state.worktrees:
        closed: list[int] = []
        for wt in session.runtime_state.worktrees:
            if not wt.branch:
                continue
            try:
                verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
            except Exception as exc:  # pragma: no cover - defensive
                failures.append(f"close-prs: {wt.branch}: {exc}")
                continue
            if verdict.closed_pr is not None and verdict.closed_pr > 0:
                closed.append(verdict.closed_pr)
            if verdict.error:
                failures.append(f"close-prs: {verdict.error}")
        for pr in closed:
            click.echo(f"closed PR #{pr}")
        if not closed:
            click.echo(f"session {session_id}: no open PRs to close")
    else:
        click.echo(f"session {session_id}: no recorded worktrees for close-prs")

    # Step 3: remove-worktrees — same as session_remove_worktrees_cmd.
    if session.runtime_state and session.runtime_state.worktrees:
        removed: list[str] = []
        for wt in session.runtime_state.worktrees:
            try:
                worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
                removed.append(wt.worktree_path)
            except (subprocess.SubprocessError, OSError) as exc:
                failures.append(f"remove-worktrees: {wt.worktree_path}: {exc}")
        for wt_path in removed:
            click.echo(f"removed worktree: {wt_path}")
        if not removed and not any(f.startswith("remove-worktrees") for f in failures):
            click.echo(f"session {session_id}: no worktrees to remove")
    else:
        click.echo(f"session {session_id}: no recorded worktrees for remove-worktrees")

    if failures:
        click.echo(
            f"session {session_id}: {len(failures)} step(s) failed during prepare-for-abandon",
            err=True,
        )
        for f in failures:
            click.echo(f"  {f}", err=True)
        raise click.ClickException(
            f"prepare-for-abandon had hard failures for {session_id}"
        )

    click.echo(f"session {session_id}: ready for abandon")


@session_cmd.command("sweep-issues-forward")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def session_sweep_issues_forward_cmd(session_id: str, project_dir: Path) -> None:
    """Drive every member issue forward to match the session's current state.

    The target issue state is derived from the session's current status
    via :func:`tripwire.core.status_contract.sweep_target_for` (e.g. a
    ``verified`` session sweeps issues to ``verified``; ``completed``
    sweeps to ``completed``). Issues already at-or-beyond the target
    are no-ops; off-path issues (``deferred``, ``abandoned``) are left
    alone — same contract as the ``sweep_issues_forward`` side-effect.

    Approach (b) per the v0.13 step-3 spec: shell out to
    ``tripwire transition issue-closure <key> <target>`` per issue. The
    ``execute_transition`` Python entry point is hardcoded to the
    ``coding-session`` workflow today (step 4 generalises it), so the
    shell hop keeps this CLI decoupled from that change. Exit code is
    inherited per-issue: any non-zero subprocess exit becomes a
    structured per-issue rejection in the summary.
    """
    from tripwire.core.status_contract import sweep_target_for

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc

    target = sweep_target_for(session.status.value)
    if target is None:
        click.echo(
            f"session {session_id}: status {session.status.value!r} has no sweep target"
        )
        return

    if not session.issues:
        click.echo(f"session {session_id}: no member issues; nothing to sweep")
        return

    rejected: list[tuple[str, str]] = []
    advanced: list[str] = []
    for issue_key in session.issues:
        try:
            result = subprocess.run(
                [
                    "tripwire",
                    "transition",
                    "issue-closure",
                    issue_key,
                    target,
                    "--project-dir",
                    str(resolved),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            rejected.append((issue_key, f"subprocess failure: {exc}"))
            continue
        if result.returncode == 0:
            advanced.append(issue_key)
            click.echo(f"advanced {issue_key} → {target}")
        else:
            reason = (result.stderr or result.stdout or "").strip() or (
                f"exit={result.returncode}"
            )
            rejected.append((issue_key, reason))

    if rejected:
        click.echo(
            f"session {session_id}: {len(rejected)} issue(s) rejected by issue-closure",
            err=True,
        )
        for key, reason in rejected:
            click.echo(f"  {key}: {reason}", err=True)
        raise click.ClickException(
            f"sweep-issues-forward rejected {len(rejected)} issue(s) for {session_id}"
        )

    click.echo(f"session {session_id}: swept {len(advanced)} issue(s) → {target}")
