"""Inline post-write hooks invoked by the workflow executor.

The v0.13 executor is an atomic primitive — no side-effect registry, no
dispatch. ``execute_transition`` calls four best-effort hooks here
inline after the status write: close engagement, audit, telemetry,
reset acks. External effects (sweep, rebase, kill, draft flips, PR
close, worktree remove, follow-up stub) live as Layer-1 CLI wrappers.
``known_ids()`` enumerates side-effect ids the schema may declare so
the ``workflow/unknown_side_effect`` lint can flag typos.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.workflow.schema import WorkflowRoute
from tripwire.models.session import AgentSession

_DECLARED_SIDE_EFFECT_IDS: frozenset[str] = frozenset(
    {
        "sweep_issues_forward",
        "rebase_pt_branch",
        "flip_drafts_to_ready",
        "flip_drafts_to_draft",
        "verify_prs_merged",
        "verify_review_ok",
        "verify_issue_artifacts",
        "kill_runtime",
        "close_open_prs",
        "remove_worktrees",
        "append_pm_followup_stub",
        "reset_acks",
        "append_audit_log_entry",
        "append_telemetry_row",
        "close_active_engagement",
    }
)


def known_ids() -> set[str]:
    """Return ids the workflow schema may declare. Static; the executor
    does not dispatch by id anymore — used by the lint to flag typos."""
    return set(_DECLARED_SIDE_EFFECT_IDS)


_ENGAGEMENT_OUTCOME_BY_TARGET = {
    "completed": "completed",
    "abandoned": "abandoned",
    "failed": "failed",
}


def close_active_engagement(
    session: AgentSession,
    route: WorkflowRoute,
    *,
    now: datetime | None = None,
) -> bool:
    """Close the last open engagement on terminal-bound transitions.

    Mirrors ``complete_session``/``abandon_session``: if the last
    engagement has no ``ended_at``, stamp it with the current time and
    derive ``outcome`` from the route's target status. Returns True iff
    the engagement was modified. No-op when target is non-terminal,
    there are no engagements, or the last engagement is already closed.
    """
    outcome = _ENGAGEMENT_OUTCOME_BY_TARGET.get(route.to_ref)
    if outcome is None:
        return False
    if not session.engagements:
        return False
    last = session.engagements[-1]
    if last.ended_at is not None:
        return False
    last.ended_at = now or datetime.now(tz=timezone.utc)
    last.outcome = outcome
    return True


def append_audit_record(
    project_dir: Path,
    *,
    session: AgentSession,
    route: WorkflowRoute,
    from_status: str,
    flags: dict,
    now: datetime | None = None,
) -> None:
    """Append a JSON line to ``.tripwire/audit.jsonl``. Best-effort.

    ``flags["action"]`` overrides the default ``transition`` action
    (e.g. ``session_reopen`` writes ``action: session_reopen``).
    """
    try:
        from tripwire.core.session_reopen import _audit_path
        from tripwire.ui.services._atomic_write import append_jsonl

        when = now or datetime.now(tz=timezone.utc)
        audit = _audit_path(project_dir)
        audit.parent.mkdir(parents=True, exist_ok=True)
        append_jsonl(
            audit,
            {
                "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "action": flags.get("action", "transition"),
                "session_id": session.id,
                "route_id": route.id,
                "from_status": from_status,
                "to_status": route.to_ref,
                "reason": flags.get("reason"),
            },
        )
    except Exception:
        pass


def append_telemetry_record(project_dir: Path, *, session: AgentSession) -> None:
    """Append a routing-telemetry row. Best-effort; telemetry must never
    block a transition. ``close_active_engagement`` must run first so
    ``duration_min`` derives from a closed engagement on terminals."""
    try:
        from tripwire.core.routing_telemetry import (
            append_telemetry_row,
            build_telemetry_row,
        )
        from tripwire.core.session_cost import compute_session_cost

        cost = compute_session_cost(project_dir, session.id).total_usd
        row = build_telemetry_row(project_dir, session, cost_usd=cost)
        append_telemetry_row(project_dir, row)
    except Exception:
        pass


def reset_acks_if_requested(
    project_dir: Path, *, session: AgentSession, flags: dict
) -> int:
    """Reset session ack markers when ``flags['reset_acks']`` is True.
    Returns the number of acks deleted. Used by the reopen route."""
    if not flags.get("reset_acks", False):
        return 0
    try:
        from tripwire.core.session_reopen import _reset_session_acks
    except ImportError:
        return 0
    reason = flags.get("reason", "session reopened")
    return _reset_session_acks(project_dir, session.id, reason)


__all__ = [
    "append_audit_record",
    "append_telemetry_record",
    "close_active_engagement",
    "known_ids",
    "reset_acks_if_requested",
]
