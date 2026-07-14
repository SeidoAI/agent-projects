"""Post-write hook: close the last open engagement on terminal transitions."""

from __future__ import annotations

from datetime import datetime, timezone

from tripwire.core.workflow.schema import WorkflowRoute
from tripwire.models.session import AgentSession

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
