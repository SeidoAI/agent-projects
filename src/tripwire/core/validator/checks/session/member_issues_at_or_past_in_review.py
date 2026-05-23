"""Backstop for the ``sweep_issues_forward`` side_effect on executing → in_review."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import (
    _issue_at_or_past,
    _session_at_or_past,
)


def check_member_issues_at_or_past_in_review(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """Sessions at-or-past ``in_review`` must have every member issue
    swept forward to at-or-past ``in_review``.

    Backstop for the ``sweep_issues_forward`` side_effect that runs on
    the ``executing → in_review`` route in v0.14.0+. If the sweep is
    bypassed for any reason (manual YAML edit, executor regression),
    this validator catches the resulting drift: a session that says
    "ready for review" while member issues are still at ``queued``
    means the per-issue artifact gates (developer.md presence) cannot
    fire, because they're keyed off issue status.

    Code: ``session/member_issue_not_swept``.
    """
    from tripwire.core.store import load_issue

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session = entity.model
        sid = session.id
        if not _session_at_or_past(ctx, str(session.status), "in_review"):
            continue

        for issue_key in session.issues:
            try:
                issue = load_issue(ctx.project_dir, issue_key)
            except FileNotFoundError:
                # Reference-integrity validators surface dangling
                # references separately; don't double-fire here.
                continue
            if _issue_at_or_past(ctx, issue.status, "in_review"):
                continue
            results.append(
                CheckResult(
                    code="session/member_issue_not_swept",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/session.yaml",
                    field="issues",
                    message=(
                        f"Session {sid!r} ({session.status}) is at-or-past "
                        f"in_review but member issue {issue_key!r} is still "
                        f"at {issue.status!r}."
                    ),
                    fix_hint=(
                        f"Run `tripwire session sweep-issues-forward {sid}` "
                        f"to move member issues to in_review, then re-validate."
                    ),
                )
            )
    return results
