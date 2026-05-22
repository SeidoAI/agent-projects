"""``tripwire session complete`` — close-out orchestration."""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.jit_prompt_state import (
    record_bypass as _record_jit_prompt_bypass,
)
from tripwire.core.jit_prompt_state import (
    write_jit_prompt_ack_marker as _write_jit_prompt_ack_marker_core,
)
from tripwire.core.session_store import load_session


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

    # v0.13.2 #2: pre-flight side-effects (flip drafts, sweep issues)
    # moved INTO ``complete_session`` so they only run after the verify
    # gates pass. Doing them here before the call left issues stuck at
    # `completed` whenever any gate later rejected.
    try:
        result = complete_session(resolved, session_id, dry_run=dry_run)
    except CompleteError as exc:
        raise click.ClickException(str(exc)) from exc

    if dry_run:
        click.echo(f"Dry run: session {session_id} can be completed.")
        if result.node_diffs:
            click.echo(f"  Node diffs to review: {len(result.node_diffs)}")
        return

    # Worktree removal stays in the CLI: it's external state cleanup,
    # not part of the verified→completed atomic step. A failure here
    # leaves an idle worktree dir, surfaced as a hygiene finding by
    # the orphan-branches lint on the next validate.
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
