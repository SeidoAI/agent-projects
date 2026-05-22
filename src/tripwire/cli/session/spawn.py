"""``tripwire session spawn`` — prep worktrees + dispatch the runtime."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import (
    _resolve_clone_path,
)
from tripwire.core.git_helpers import commit_and_push_file
from tripwire.core.session_check import any_blocking_error, strict_check
from tripwire.core.session_store import load_session, save_session
from tripwire.models.session import EngagementEntry


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

    # v0.13.2 — persist runtime_state to the PT worktree so the draft PR
    # carries it. Without this, the field lives only as an uncommitted
    # edit in the main checkout and gets wiped the next time main pulls
    # (or worse, when the draft PR squash-merges and overwrites the
    # tracked file). Failure here logs a WARNING but doesn't fail the
    # spawn — the agent is already running and runtime_state is on disk
    # in the main checkout; the operator can recover by hand.
    pt_entry = next(
        (wt for wt in start_result.worktrees if wt.branch.startswith("proj/")),
        None,
    )
    if pt_entry is not None:
        from tripwire.core.session_store import session_yaml_path

        pt_path = Path(pt_entry.worktree_path)
        save_session(pt_path, session, update_cache=False)
        try:
            commit_and_push_file(
                pt_path,
                session_yaml_path(pt_path, session_id),
                f"session({session_id}): capture runtime_state from spawn",
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip() or str(exc)
            click.echo(
                f"WARNING: failed to commit runtime_state in PT worktree "
                f"{pt_path}: {detail}. runtime_state.claude_session_id "
                f"may be lost on next PR merge; commit manually with "
                f"`git -C {pt_path} add {session_yaml_path(pt_path, session_id).relative_to(pt_path)} "
                f"&& git -C {pt_path} commit -m 'session({session_id}): capture runtime_state' "
                f"&& git -C {pt_path} push`.",
                err=True,
            )

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
