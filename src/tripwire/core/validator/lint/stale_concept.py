"""KUI-144 (D2) — concept node is stale AND referenced by active work.

The plain ``check_freshness`` rule warns on EVERY stale node, which
adds noise on long-lived nodes that no one is actively touching. This
lint narrows the signal: warn only when the stale node is currently
referenced by at least one active issue or session, because that's
where the staleness will actually mislead someone.

"Active" means:
- Issue: status not in {done, canceled}.
- Session: status not in {completed, abandoned, failed}.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tripwire.core.freshness import check_all_nodes
from tripwire.core.graph.refs import extract_references
from tripwire.models.graph import FreshnessStatus

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


_INACTIVE_ISSUE = {"done", "canceled"}
_TERMINAL_SESSION = {"completed", "abandoned", "failed"}


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if ctx.project_config is None or not ctx.nodes:
        return []

    nodes = [e.model for e in ctx.nodes]
    rel_by_id = {e.model.id: e.rel_path for e in ctx.nodes}

    stale_ids: set[str] = set()
    for fr in check_all_nodes(nodes, ctx.project_config):
        if fr.status == FreshnessStatus.STALE:
            stale_ids.add(fr.node_id)
    if not stale_ids:
        return []

    references = _node_references(ctx, stale_ids)
    results: list[CheckResult] = []
    for node_id in sorted(stale_ids):
        sources = references.get(node_id)
        if not sources:
            continue
        results.append(
            CheckResult(
                code="stale_concept/referenced",
                severity="warning",
                file=rel_by_id.get(node_id),
                field="source.content_hash",
                message=(
                    f"Concept node {node_id!r} is stale and is still "
                    f"referenced by active work: {', '.join(sorted(sources))}. "
                    f"Refresh the node before resuming the referenced work."
                ),
                fix_hint=(
                    "Run `tripwire node check --update` to recompute the "
                    "node's content_hash, or update the source pointer."
                ),
            )
        )
    return results


def _node_references(
    ctx: ValidationContext, candidate_ids: set[str]
) -> dict[str, set[str]]:
    """Map candidate node id → set of active referrer ids (issues + sessions)."""
    out: dict[str, set[str]] = {nid: set() for nid in candidate_ids}
    for entity in ctx.issues:
        status = str(getattr(entity.model, "status", ""))
        if status in _INACTIVE_ISSUE:
            continue
        for ref in extract_references(entity.body or ""):
            if ref in out:
                out[ref].add(entity.model.id)
    for entity in ctx.sessions:
        status = str(getattr(entity.model, "status", ""))
        if status in _TERMINAL_SESSION:
            continue
        for ref in extract_references(entity.body or ""):
            if ref in out:
                out[ref].add(entity.model.id)
    return out
