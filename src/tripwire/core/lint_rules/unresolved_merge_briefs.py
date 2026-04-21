"""lint/unresolved_merge_briefs — error when handoff is attempted with
pending merge briefs in the project.

Prevents /pm-session-queue when .tripwire/merge-briefs/*.yaml files exist.
Forces the agent to resolve (via /pm-project-sync) or explicitly abandon
before launching execution.
"""

from __future__ import annotations

from tripwire.core.linter import LintFinding, register_rule
from tripwire.core.merge_brief import list_pending_briefs


@register_rule(
    stage="handoff",
    code="lint/unresolved_merge_briefs",
    severity="error",
)
def _check(ctx):
    for node_id in list_pending_briefs(ctx.project_dir):
        yield LintFinding(
            code="lint/unresolved_merge_briefs",
            severity="error",
            message=f"merge brief pending for {node_id}",
            file=f".tripwire/merge-briefs/{node_id}.yaml",
            fix_hint=(
                "Run /pm-project-sync to resolve, or delete the brief to "
                "abandon the pull."
            ),
        )
