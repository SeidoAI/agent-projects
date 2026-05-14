"""Move a completed session back to ``paused`` for PR-fix iteration.

The companion to ``session complete``: when a PR review surfaces fixes,
this resets the lifecycle so ``session spawn <id> --resume`` can
re-engage the agent. Side-effects (each best-effort):

- Status: ``completed`` → ``paused`` (via the workflow executor).
- A ``## PM follow-up`` section is appended to plan.md if absent.
- One JSON line is appended to
  ``$TRIPWIRE_LOG_DIR/<project-slug>/audit.jsonl`` (or
  ``~/.tripwire/logs/...`` when unset) recording the reason + timestamp.

v0.13: The ``ready→draft`` flip for recorded draft PRs is now a
separate Layer-1 step (``tripwire session flip-drafts-draft``), which
the CLI wrapper invokes before this helper. Ack reset is fired by the
executor's ``reset_acks_if_requested`` post-write hook (via the
``flags['reset_acks']`` flag).

The CLI wrapper at ``cli/session.py:session_reopen_cmd`` parses args,
calls :func:`reopen_session`, and prints the success line. All
business logic lives here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core import paths
from tripwire.core.session_store import load_session
from tripwire.core.store import load_project
from tripwire.models.enums import SessionStatus


@dataclass
class ReopenResult:
    """Side-effect summary returned to the CLI for user-facing output."""

    session_id: str
    new_status: SessionStatus
    audit_path: Path
    plan_updated: bool
    draft_prs_flipped: list[str] = field(default_factory=list)
    # KUI-137 (B3): count of `.tripwire/acks/*-<sid>.json` markers
    # deleted when the caller passed `reset_acks=True`. Always 0 in
    # the default-flag case.
    acks_reset_count: int = 0


def reopen_session(
    project_dir: Path,
    session_id: str,
    reason: str,
    *,
    reset_acks: bool = False,
) -> ReopenResult:
    """Flip a completed session back to ``paused`` and arm the resume path.

    When ``reset_acks=True`` (KUI-137), every per-session tripwire ack
    marker (files named ``<workflow>-<session-id>-<tripwire-id>.json``
    under ``<project_dir>/.tripwire/acks/``) is deleted before the
    audit-log entry is written, and a ``session.acks_reset`` event is
    emitted. Use this after substantial rework so the agent
    re-encounters every tripwire fresh on resume.

    Raises:
        FileNotFoundError: session.yaml does not exist.
        ValueError: session is not currently at ``status: completed``.
    """
    session = load_session(project_dir, session_id)

    if session.status != SessionStatus.COMPLETED:
        raise ValueError(
            f"session '{session_id}' is '{session.status}', must be "
            f"'completed' to reopen"
        )

    # v0.13: the ready→draft flip moved to the Layer-1 CLI
    # ``tripwire session flip-drafts-draft``; the CLI wrapper for
    # reopen invokes it before us. Keep an empty list so the result
    # shape is unchanged for the CLI's summary block.
    flipped: list[str] = []

    # Append a `## PM follow-up` stub to plan.md when missing so the
    # resumed agent has a place to read PM directives even if the PM
    # forgot to add one.
    plan_updated = False
    plan_path = paths.session_plan_path(project_dir, session_id)
    if plan_path.is_file():
        plan_text = plan_path.read_text(encoding="utf-8")
        if "## PM follow-up" not in plan_text:
            pr_lines = [
                f"- {wt.draft_pr_url}"
                for wt in session.runtime_state.worktrees
                if wt.draft_pr_url
            ]
            stub_lines = ["", "## PM follow-up", "", f"Reopened: {reason}.", ""]
            if pr_lines:
                stub_lines.append("PR(s) under review:")
                stub_lines.extend(pr_lines)
                stub_lines.append("")
            # v0.12.1: tell the resumed agent + future PM what's about
            # to happen on the next spawn. `tripwire session complete`
            # cleans the worktrees; `--resume` recreates them off
            # latest origin/main. The agent should open a NEW fix
            # branch inside the recreated worktree, not push to the
            # merged branch.
            stub_lines.append(
                "Worktrees were cleaned at completion. They will be "
                "recreated off latest `origin/main` on the next "
                "`tripwire session spawn <sid> --resume`. Open a new "
                "fix branch inside the recreated worktree; do NOT push "
                "to the merged branch."
            )
            stub_lines.append("")
            stub_lines.append(
                "Address each PM finding in priority order; see the "
                "PR comments for specifics."
            )
            stub_lines.append("")
            sep = "" if plan_text.endswith("\n") else "\n"
            plan_path.write_text(
                plan_text + sep + "\n".join(stub_lines), encoding="utf-8"
            )
            plan_updated = True

    # v0.13: status flip goes through ``execute_transition`` — the sole
    # writer of ``session.status``. The executor's post-write hooks
    # take care of the audit log row (``action`` and ``reason`` come
    # from the flags below) so we don't write a separate row here.
    # We still own the ack reset because the executor's hook returns
    # the deleted count but doesn't surface it to the caller.
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    try:
        transition = execute_transition(
            project_dir,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="paused",
            flags={"action": "session_reopen", "reason": reason},
        )
    except TransitionError as exc:
        raise ValueError(f"executor refused reopen: {exc}") from exc
    if not transition.ok:
        raise ValueError(
            f"transition to paused rejected: "
            f"{transition.message or transition.reason}"
        )

    # KUI-137: optional ack reset AFTER the transition so the event
    # ordering still reflects what the agent will see on resume.
    acks_reset_count = 0
    if reset_acks:
        acks_reset_count = _reset_session_acks(project_dir, session_id, reason)

    audit_path = _audit_path(project_dir)

    return ReopenResult(
        session_id=session_id,
        new_status=SessionStatus.PAUSED,
        audit_path=audit_path,
        plan_updated=plan_updated,
        draft_prs_flipped=flipped,
        acks_reset_count=acks_reset_count,
    )


def _reset_session_acks(project_dir: Path, session_id: str, reason: str) -> int:
    """Delete `<project_dir>/.tripwire/acks/<workflow>-<session_id>-*.json` markers.

    v0.13.1 the marker name is keyed by (workflow, instance, prompt);
    matching by the ``-<session_id>-`` infix selects every prompt's
    ack across all workflows for this instance.

    Returns the count of markers deleted. Also emits one
    ``session_acks_reset`` event (skipped when zero markers existed —
    no event for a no-op).
    """
    from tripwire.core.event_emitter import FileEmitter

    acks_dir = project_dir / paths.ACKS_SUBDIR
    infix = f"-{session_id}-"
    deleted = 0
    if acks_dir.is_dir():
        for marker in acks_dir.iterdir():
            if not (marker.is_file() and marker.name.endswith(".json")):
                continue
            # Match `<workflow>-<sid>-<prompt>.json` exactly: the
            # session id must be the middle segment, sandwiched
            # between two hyphens. An infix substring match is enough
            # because workflow ids and prompt ids never embed dashes
            # adjacent to the session id boundary in v0.13.1.
            if infix in marker.name:
                try:
                    marker.unlink()
                    deleted += 1
                except OSError:
                    # A marker we can't remove doesn't sink the reopen —
                    # the agent will still see the prompt and the marker
                    # path will simply still be substantive.
                    continue

    payload = {
        "kind": "session_acks_reset",
        "session_id": session_id,
        "reason": reason,
        "acks_reset_count": deleted,
        "fired_at": datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
    }
    FileEmitter(project_dir).emit("session_acks_reset", payload)
    return deleted


def _audit_path(project_dir: Path) -> Path:
    """Resolve the audit JSONL path for *project_dir*'s log root."""
    try:
        proj = load_project(project_dir)
        proj_slug = proj.name.lower().replace(" ", "-")
    except Exception:
        proj_slug = "unknown"
    override = os.environ.get("TRIPWIRE_LOG_DIR")
    log_root = Path(override) if override else Path.home() / ".tripwire" / "logs"
    return log_root / proj_slug / "audit.jsonl"
