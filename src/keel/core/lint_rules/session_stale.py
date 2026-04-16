"""lint/session_stale — warn when a session has been in the
``implementing`` state for longer than the threshold.

Used to surface sessions that may be stuck or abandoned. Only runs
for session-stage lint (requires a session_id in context).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from keel.core.linter import LintFinding, register_rule
from keel.core.session_store import load_session

STALE_DAYS = 3


@register_rule(stage="session", code="lint/session_stale", severity="warning")
def _check(ctx):
    if ctx.session_id is None:
        return
    session = load_session(ctx.project_dir, ctx.session_id)
    if session.status != "implementing":
        return
    if session.updated_at is None:
        return
    updated = session.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = datetime.now(tz=timezone.utc) - updated
    if age > timedelta(days=STALE_DAYS):
        yield LintFinding(
            code="lint/session_stale",
            severity="warning",
            message=(
                f"session {session.id} has been in implementing for "
                f"{age.days} days (threshold {STALE_DAYS})."
            ),
            file=f"sessions/{session.id}/session.yaml",
            fix_hint=(
                "Check session progress; consider splitting the work or "
                "re-engaging the agent."
            ),
        )
