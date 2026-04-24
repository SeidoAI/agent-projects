"""Extract concept-graph references from a session's plan.md.

Shared utility used by:
- `tripwire validate-plan` (checks every reference resolves to a real node)
- `tripwire.runtimes.prep.render_claude_md` (lists referenced nodes in
  the agent's CLAUDE.md so the agent reads them at session start)

The v0.7.3 implementation returns id + node-file path + existence flag.
The v0.8 spec (`docs/superpowers/specs/2026-04-24-v08-bidirectional-concept-graph.md`
§7.1) extends this dataclass with `version_pinned`, `current_version`,
and `is_stale` fields — additive, no consumer breakage.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tripwire.core.node_store import node_exists, node_path
from tripwire.core.paths import session_plan_path
from tripwire.core.reference_parser import extract_references


@dataclass(frozen=True)
class ConceptContextEntry:
    """One [[ref]] from a plan, with resolution info.

    v0.8 will add `version_pinned: int | None`, `current_version: int`,
    `is_stale: bool` per the bi-directional concept graph spec.
    """

    id: str
    node_path: Path
    exists: bool


def extract_plan_concepts(
    project_dir: Path,
    session_id: str,
) -> list[ConceptContextEntry]:
    """Return one entry per unique [[ref]] in the session's plan.md.

    Order is preserved (first occurrence wins). Duplicates are dropped.
    If the plan file does not exist, returns an empty list — the caller
    decides whether absence is an error (validate-plan) or a no-op
    (CLAUDE.md prep).
    """
    plan_path = session_plan_path(project_dir, session_id)
    if not plan_path.is_file():
        return []
    body = plan_path.read_text(encoding="utf-8")
    refs = extract_references(body)
    # Preserve first-occurrence order, drop duplicates.
    seen: set[str] = set()
    unique_ids: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            unique_ids.append(ref)
    return [
        ConceptContextEntry(
            id=node_id,
            node_path=node_path(project_dir, node_id),
            exists=node_exists(project_dir, node_id),
        )
        for node_id in unique_ids
    ]
