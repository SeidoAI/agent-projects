"""Bidirectional ``related`` consistency between concept nodes."""

from __future__ import annotations

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.node import ConceptNode


def check_bidirectional_related(ctx: ValidationContext) -> list[CheckResult]:
    """For every node A.related: [B], node B.related must contain A."""
    results: list[CheckResult] = []
    by_id = {e.model.id: e for e in ctx.nodes}
    for entity in ctx.nodes:
        node: ConceptNode = entity.model
        for related_id in node.related:
            other = by_id.get(related_id)
            if other is None:
                continue  # caught by ref integrity
            if node.id not in other.model.related:
                results.append(
                    CheckResult(
                        code="bidi/related",
                        severity="warning",
                        file=entity.rel_path,
                        field="related",
                        message=(
                            f"Node {node.id!r} declares related {related_id!r}, "
                            f"but {related_id!r} does not declare {node.id!r} in its related list."
                        ),
                        fix_hint="Run with --fix to add the missing back-reference.",
                    )
                )
    return results
