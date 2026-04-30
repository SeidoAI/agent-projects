"""KUI-147 (D5) — issue has accreted too many children or sessions.

When an issue grows ``max_children + 1`` sub-issues (other issues
whose ``parent`` field points at it) OR ``max_sessions + 1`` sessions
implementing it, the lint suggests a breakdown. The PM is the one
who decides whether to act — the lint is advisory.

Thresholds come from
:mod:`tripwire.core.validator.lint._thresholds.DEFAULT_THRESHOLDS`
under the ``mega_issue`` key (overrideable via
``project.yaml.lint_config`` in D7).
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from tripwire.core.validator.lint._thresholds import get_threshold

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if not ctx.issues:
        return []

    max_children = get_threshold(
        ctx.project_config, "mega_issue", "max_children"
    )
    if max_children is None:
        max_children = 8
    max_sessions = get_threshold(
        ctx.project_config, "mega_issue", "max_sessions"
    )
    if max_sessions is None:
        max_sessions = 6

    children_by_parent: dict[str, list[str]] = defaultdict(list)
    for entity in ctx.issues:
        parent = getattr(entity.model, "parent", None)
        if parent:
            children_by_parent[parent].append(entity.model.id)

    sessions_by_issue: dict[str, list[str]] = defaultdict(list)
    for entity in ctx.sessions:
        for issue_id in getattr(entity.model, "issues", []) or []:
            sessions_by_issue[issue_id].append(entity.model.id)

    rel_by_id = {e.model.id: e.rel_path for e in ctx.issues}
    results: list[CheckResult] = []

    for issue_id, children in sorted(children_by_parent.items()):
        if len(children) <= max_children:
            continue
        results.append(
            CheckResult(
                code="mega_issue/too_many_children",
                severity="warning",
                file=rel_by_id.get(issue_id),
                field="parent",
                message=(
                    f"Issue {issue_id!r} has {len(children)} child issue(s) "
                    f"(threshold {max_children}). Consider promoting it to "
                    f"an epic and grouping the children under sub-epics."
                ),
            )
        )

    for issue_id, sessions in sorted(sessions_by_issue.items()):
        if len(sessions) <= max_sessions:
            continue
        results.append(
            CheckResult(
                code="mega_issue/too_many_sessions",
                severity="warning",
                file=rel_by_id.get(issue_id),
                field="issues",
                message=(
                    f"Issue {issue_id!r} is implemented by {len(sessions)} "
                    f"session(s) (threshold {max_sessions}). Sessions are "
                    f"meant to be small — break this issue into independent "
                    f"slices."
                ),
            )
        )

    return results
