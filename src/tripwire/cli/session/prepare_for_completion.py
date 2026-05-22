"""``tripwire session prepare-for-completion`` — pre-flight the completed transition.

Layer-2 chain: validate (selector-filtered) → flip-drafts-ready →
per-PR merge readiness via ``gh pr view``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


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

    resolved, session = _resolve_and_load_session(project_dir, session_id)

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
