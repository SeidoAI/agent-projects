"""Coverage warnings: issues with no node refs, nodes referenced ≤ 1 time."""

from __future__ import annotations

from tripwire.core.graph.refs import extract_references
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.enums import DEFINITIONAL_NODE_TYPES


def check_coverage_heuristics(ctx: ValidationContext) -> list[CheckResult]:
    """Coverage warnings — hint at potential semantic gaps."""
    results: list[CheckResult] = []

    # Build reference counts from issue bodies
    node_ids = {e.raw_frontmatter.get("id", "") for e in ctx.nodes}
    node_ref_counts: dict[str, int] = dict.fromkeys(node_ids, 0)

    for entity in ctx.issues:
        refs = extract_references(entity.body)
        issue_has_node_ref = False
        for ref in refs:
            if ref in node_ref_counts:
                node_ref_counts[ref] += 1
                issue_has_node_ref = True
        if not issue_has_node_ref and entity.body.strip():
            results.append(
                CheckResult(
                    code="coverage/no_nodes_referenced",
                    severity="warning",
                    file=entity.rel_path,
                    message=(
                        "Issue body contains no [[node-id]] references. "
                        "Consider linking to relevant concept nodes."
                    ),
                )
            )

    for nid, count in node_ref_counts.items():
        if count <= 1 and nid:
            node_entity = next(
                (e for e in ctx.nodes if e.raw_frontmatter.get("id") == nid),
                None,
            )
            if node_entity:
                # Definitional types (principle / glossary / persona /
                # invariant / anti_pattern / practice / metric / skill)
                # are reference surfaces, not implementation targets.
                # `coverage/unreferenced_node` was designed to warn when
                # a code-anchored node has no implementing issue — a
                # `principle-pm-curates-attention` legitimately has none.
                node_type = str(node_entity.raw_frontmatter.get("type", "") or "")
                if node_type in DEFINITIONAL_NODE_TYPES:
                    continue
                results.append(
                    CheckResult(
                        code="coverage/unreferenced_node",
                        severity="warning",
                        file=node_entity.rel_path,
                        message=(
                            f"Concept node '{nid}' is referenced by only "
                            f"{count} issue(s). Consider whether other issues "
                            f"should reference it, or merge it."
                        ),
                    )
                )

    return results
