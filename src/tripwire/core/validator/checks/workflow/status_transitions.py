"""Issue status reachability via the project's issue-closure workflow."""

from __future__ import annotations

from tripwire.core.status import build_issue_transitions, is_status_reachable
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.issue import Issue


def check_status_transitions(ctx: ValidationContext) -> list[CheckResult]:
    """Every issue's status must be reachable via the issue-closure workflow.

    Reachability is derived from ``workflow.yaml``'s ``issue-closure``
    workflow routes.

    Projects without an ``issue-closure`` workflow get the
    "trivially reachable" fallback (every declared status counts), so
    the check is a no-op rather than failing every issue.
    """
    if ctx.project_config is None:
        return []
    transitions = build_issue_transitions(ctx.project_dir)
    declared = list(ctx.project_config.statuses)
    results: list[CheckResult] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if not is_status_reachable(
            transitions, issue.status, declared_statuses=declared
        ):
            results.append(
                CheckResult(
                    code="status/unreachable",
                    severity="error",
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Issue status {issue.status!r} is not reachable from "
                        f"the start state via the issue-closure workflow "
                        f"routes in workflow.yaml."
                    ),
                    fix_hint=(
                        "Check the issue-closure workflow's `routes:` block "
                        "in workflow.yaml or fix the issue's status."
                    ),
                )
            )
    return results
