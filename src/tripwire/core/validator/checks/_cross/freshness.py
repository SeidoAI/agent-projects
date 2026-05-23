"""Concept-node freshness: live ``content_hash`` matches recorded value."""

from __future__ import annotations

from tripwire.core import freshness as freshness_mod
from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext


def check_freshness(ctx: ValidationContext) -> list[CheckResult]:
    """Concept node freshness — content_hash must match live content."""
    if ctx.project_config is None:
        return []
    results: list[CheckResult] = []
    nodes = [e.model for e in ctx.nodes]
    rel_by_id = {e.model.id: e.rel_path for e in ctx.nodes}
    for fr in freshness_mod.check_all_nodes(nodes, ctx.project_config):
        rel = rel_by_id.get(fr.node_id, f"{paths.NODES_DIR}/{fr.node_id}.yaml")
        if fr.status == freshness_mod.FreshnessStatus.SOURCE_MISSING:
            results.append(
                CheckResult(
                    code="freshness/source_missing",
                    severity="error",
                    file=rel,
                    field="source",
                    message=fr.detail or f"Source missing for node {fr.node_id}.",
                )
            )
        elif fr.status == freshness_mod.FreshnessStatus.STALE:
            results.append(
                CheckResult(
                    code="freshness/stale",
                    severity="warning",
                    file=rel,
                    field="source.content_hash",
                    message=fr.detail or f"Node {fr.node_id} content_hash is stale.",
                    fix_hint="Run `tripwire node check --update` (deferred to a later release).",
                )
            )
    return results
