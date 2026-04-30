"""KUI-148 (D6) — concept-node ÷ active-issue ratio is out of band.

The healthy ratio depends on the project type. A product PT often
has many issues per node (concepts are stable, work is iterative); a
library PT typically has more nodes per issue (each public surface
is a node). The lint reads ``project.yaml.metadata.kind`` and applies
the band from
:mod:`tripwire.core.validator.lint._thresholds.KIND_OVERRIDES`,
falling back to the default band for unknown kinds.

Silent on small projects (fewer than 5 active issues) — the ratio
swings wildly there and the signal is meaningless.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tripwire.core.validator.lint._thresholds import get_threshold

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


_INACTIVE_ISSUE = {"done", "canceled"}
_MIN_ACTIVE_ISSUES = 5
_PROJECT_YAML = "project.yaml"


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    active_issues = sum(
        1
        for e in ctx.issues
        if str(getattr(e.model, "status", "")) not in _INACTIVE_ISSUE
    )
    if active_issues < _MIN_ACTIVE_ISSUES:
        return []

    node_count = len(ctx.nodes)
    ratio = node_count / active_issues

    min_ratio = get_threshold(ctx.project_config, "node_ratio", "min_ratio")
    if min_ratio is None:
        min_ratio = 0.10
    max_ratio = get_threshold(ctx.project_config, "node_ratio", "max_ratio")
    if max_ratio is None:
        max_ratio = 5.0

    results: list[CheckResult] = []
    if ratio < min_ratio:
        results.append(
            CheckResult(
                code="node_ratio/below_band",
                severity="warning",
                file=_PROJECT_YAML,
                field="metadata.kind",
                message=(
                    f"Concept-node-to-issue ratio is {ratio:.2f} "
                    f"({node_count} nodes / {active_issues} active issues); "
                    f"expected ≥ {min_ratio:.2f}. Capture more concepts as "
                    f"nodes so issues link to durable definitions."
                ),
            )
        )
    elif ratio > max_ratio:
        results.append(
            CheckResult(
                code="node_ratio/above_band",
                severity="warning",
                file=_PROJECT_YAML,
                field="metadata.kind",
                message=(
                    f"Concept-node-to-issue ratio is {ratio:.2f} "
                    f"({node_count} nodes / {active_issues} active issues); "
                    f"expected ≤ {max_ratio:.2f}. Some nodes may be stale "
                    f"or duplicate — prune or merge."
                ),
            )
        )
    return results
