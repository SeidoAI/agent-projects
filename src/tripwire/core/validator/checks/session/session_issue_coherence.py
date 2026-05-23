"""Layer-3 coherence (v0.7b §6.4): session.status vs. referenced issue statuses."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.session import AgentSession

# v0.7b Layer-3 coherence matrix — spec §6.4.
#
# Matrix is keyed by *phase* (5 values per spec table), not by the full
# SessionStatus enum. SessionStatus values map to a phase via
# _SESSION_STATUS_TO_PHASE. Session statuses not in the mapping are
# off-lifecycle (failed, paused, abandoned, re_engaged, waiting_for_*)
# and skip coherence checking entirely.
#
# Verdict:
#   "ok"           — aligned
#   "ahead_warn"   — issue later in lifecycle than session; surfaces as
#                    `coherence/issue_status_ahead_of_session` (warning).
#   "behind_error" — issue earlier than session; surfaces as
#                    `coherence/issue_status_lags_session` (error).
#
# Spec §6.4 table:
#   planned      → warn on later
#   in_progress  → warn on later
#   in_review    → error on earlier
#   verified     → error on earlier
#   done         → error on anything else

_SESSION_STATUS_TO_PHASE: dict[str, str] = {
    "planned": "planned",
    "queued": "executing",
    "executing": "executing",
    "in_review": "in_review",
    "verified": "verified",
    "completed": "completed",
    # Off-lifecycle statuses (failed, paused, abandoned) are deliberately
    # omitted — coherence is meaningless there.
}

_COHERENCE_MATRIX: dict[str, dict[str, str]] = {
    "planned": {
        "planned": "ok",
        "queued": "ok",
        "executing": "ahead_warn",
        "in_review": "ahead_warn",
        "verified": "ahead_warn",
        "completed": "ahead_warn",
    },
    "executing": {
        "planned": "behind_error",
        "queued": "ok",
        "executing": "ok",
        "in_review": "ok",
        "verified": "ahead_warn",
        "completed": "ahead_warn",
    },
    "in_review": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "ok",
        "verified": "ok",
        "completed": "ok",
    },
    "verified": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "behind_error",
        "verified": "ok",
        "completed": "ok",
    },
    "completed": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "behind_error",
        "verified": "behind_error",
        "completed": "ok",
    },
}


def check_session_issue_coherence(ctx: ValidationContext) -> list[CheckResult]:
    """Layer-3 coherence: session.status vs. referenced issue statuses.

    Emits `coherence/issue_status_lags_session` (error) when an issue is
    behind where the session claims it should be; and
    `coherence/issue_status_ahead_of_session` (warning) when an issue is
    further along than the session stage would suggest.

    Sessions in statuses not listed in the matrix (`failed`, `waiting_for_*`,
    `paused`, `abandoned`, `re_engaged`) are skipped — those are off-lifecycle
    states where alignment isn't meaningful.
    """
    results: list[CheckResult] = []
    issues_by_key = {entity.model.id: entity.model for entity in ctx.issues}
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        phase = _SESSION_STATUS_TO_PHASE.get(str(session.status))
        if phase is None:
            continue
        session_row = _COHERENCE_MATRIX[phase]
        for issue_key in session.issues:
            issue = issues_by_key.get(issue_key)
            if issue is None:
                continue
            verdict = session_row.get(str(issue.status), "ok")
            if verdict == "ok":
                continue
            if verdict == "behind_error":
                code = "coherence/issue_status_lags_session"
                severity = "error"
                direction = "issue lags session"
            else:  # "ahead_warn"
                code = "coherence/issue_status_ahead_of_session"
                severity = "warning"
                direction = "issue is ahead of session"
            results.append(
                CheckResult(
                    code=code,
                    severity=severity,
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Session {session.id!r} ({session.status}) has issue "
                        f"{issue_key!r} at {issue.status!r} — {direction}."
                    ),
                    fix_hint=(
                        "Advance the issue status to match, or step the session "
                        "status back to a phase that matches the issue."
                    ),
                )
            )
    return results
