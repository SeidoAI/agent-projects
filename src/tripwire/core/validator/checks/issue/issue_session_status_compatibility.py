"""v0.9.4 — every member issue's status must be compatible with the session's."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext


def check_issue_session_status_compatibility(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """Contract: every member issue's status must be in the set allowed
    for its session's status. Catches contract violations on write.
    """
    from tripwire.core.status_contract import (
        ALLOWED_ISSUE_STATES_BY_SESSION_STATE,
        is_issue_state_compatible_with_session_state,
    )

    results: list[CheckResult] = []
    issues_by_key = {entity.model.id: entity for entity in ctx.issues}
    for session_entity in ctx.sessions:
        session = session_entity.model
        s_state = str(session.status)
        if s_state not in ALLOWED_ISSUE_STATES_BY_SESSION_STATE:
            # Unknown session state — not our problem here. Other checks
            # cover unknown enum values.
            continue
        for issue_key in session.issues:
            issue_entity = issues_by_key.get(issue_key)
            if issue_entity is None:
                continue
            issue = issue_entity.model
            if not is_issue_state_compatible_with_session_state(
                str(session.status), str(issue.status)
            ):
                allowed = sorted(ALLOWED_ISSUE_STATES_BY_SESSION_STATE[s_state])
                results.append(
                    CheckResult(
                        code="contract/issue_session_state_incompatible",
                        severity="error",
                        file=session_entity.rel_path,
                        field="status",
                        message=(
                            f"Session {session.id!r} ({session.status}) has "
                            f"issue {issue_key!r} at {issue.status!r} — "
                            f"not in the allowed set for session state "
                            f"{s_state!r}: {allowed}."
                        ),
                        fix_hint=(
                            "Run `tripwire session transition` to a status "
                            "whose route declares `sweep_issues_forward`, "
                            "or advance the issue status directly to match "
                            "the contract."
                        ),
                    )
                )
    return results
