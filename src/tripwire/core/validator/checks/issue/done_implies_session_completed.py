"""v0.9.4 — an issue at ``completed`` belongs to a completed session."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext


def check_done_implies_session_completed(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """An issue at ``completed`` should belong to at least one session
    that's also ``completed`` (or no session at all).

    Catches "orphan completion" cases where an issue was flipped to
    completed manually without the session being walked through to its
    own terminal state.
    """
    results: list[CheckResult] = []
    sessions_by_issue: dict[str, list[str]] = {}
    for session_entity in ctx.sessions:
        session = session_entity.model
        s_state = str(session.status)
        for issue_key in session.issues:
            sessions_by_issue.setdefault(issue_key, []).append(s_state)

    for entity in ctx.issues:
        issue = entity.model
        if str(issue.status) != "completed":
            continue
        owning_states = sessions_by_issue.get(issue.id, [])
        if not owning_states:
            # Issue has no sessions claiming it — orphan-completion is
            # still legitimate (e.g. closed without ever being session-owned).
            continue
        if "completed" in owning_states or "abandoned" in owning_states:
            continue
        results.append(
            CheckResult(
                code="contract/done_implies_session_completed",
                severity="warning",
                file=entity.rel_path,
                field="status",
                message=(
                    f"Issue {issue.id!r} is at 'completed' but no owning "
                    f"session is in {{completed, abandoned}}. "
                    f"Owning session states: {sorted(owning_states)}."
                ),
                fix_hint=(
                    "Walk the owning session through its terminal "
                    "transition, or move the issue back if the session "
                    "isn't actually done."
                ),
            )
        )
    return results
