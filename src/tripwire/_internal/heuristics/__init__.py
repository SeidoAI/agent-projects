"""Heuristic primitive: soft warn-once detectors.

A heuristic is the soft sibling of a tripwire. Where a tripwire returns a
hard pass/fail verdict, a heuristic *warns* — it surfaces a finding the
agent should consider but not necessarily act on. Heuristics are
suppressible per ``(heuristic_id, entity_uuid, condition_hash)`` triple
via a marker file under ``.tripwire/heuristic-acks/``; the marker
re-fires the moment the condition_hash changes (the underlying evidence
moved), so suppression decays automatically when the situation evolves.

Stage 1 ships the framework. The 8 existing soft ``v_*`` checks (lifted
from ``core/validator/lint/`` and ``core/validator/checks/``) are
declared here and wired through the marker layer. Future stages
introduce purely-heuristic detectors that have no underlying validator.

The four-primitive vocabulary (recap):

* tripwire     — hard pass/fail gate
* **heuristic** — soft warn-once detector (this module)
* jit_prompt   — hidden + ack
* prompt_check — required slash command
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from tripwire._internal.heuristics._acks import (
    gc_markers,
    has_marker,
    marker_path,
    reset_markers,
    write_marker,
)


@dataclass(frozen=True)
class HeuristicSpec:
    """Static description of a heuristic.

    ``check_code_prefix`` is the prefix of validator ``CheckResult.code``
    values produced by the underlying detector (e.g. ``"stale_concept"``
    for results coded ``"stale_concept/referenced"``). The marker layer
    uses this prefix to decide which findings the heuristic id covers.
    """

    id: str
    label: str
    description: str
    entity: str  # "issue" | "session" | "node" | "project"
    check_code_prefix: str


_REGISTRY: tuple[HeuristicSpec, ...] = (
    HeuristicSpec(
        id="v_stale_concept",
        label="Stale concept",
        description=(
            "Concept node referenced by an active issue/session has not "
            "been refreshed in a while; the cited body may no longer "
            "match the source it points at."
        ),
        entity="node",
        check_code_prefix="stale_concept",
    ),
    HeuristicSpec(
        id="v_concept_name_prose",
        label="Concept name in prose",
        description=(
            "Issue/session prose mentions a node name without a "
            "structured reference; consider linking the node so the "
            "graph picks it up."
        ),
        entity="issue",
        check_code_prefix="concept_name_prose",
    ),
    HeuristicSpec(
        id="v_semantic_coverage",
        label="Semantic coverage",
        description=(
            "Issue acceptance criteria reference fewer concept nodes "
            "than the configured threshold; AC may under-specify the "
            "concepts in play."
        ),
        entity="issue",
        check_code_prefix="semantic_coverage",
    ),
    HeuristicSpec(
        id="v_mega_issue",
        label="Mega-issue",
        description=(
            "Issue has child issues or sessions over the configured "
            "limit; consider splitting before scoping further."
        ),
        entity="issue",
        check_code_prefix="mega_issue",
    ),
    HeuristicSpec(
        id="v_node_ratio",
        label="Node ratio",
        description=(
            "Concept-node count vs issue count is outside the configured "
            "band for the project type; signals over- or under-modelling."
        ),
        entity="project",
        check_code_prefix="node_ratio",
    ),
    HeuristicSpec(
        id="v_coverage_heuristics",
        label="Coverage heuristics",
        description=(
            "Test/verification coverage looks light relative to the "
            "session's scope and acceptance criteria."
        ),
        entity="session",
        check_code_prefix="coverage_heuristics",
    ),
    HeuristicSpec(
        id="v_quality_consistency",
        label="Quality consistency",
        description=(
            "Issue scoping quality varies materially from the project's "
            "calibrated baseline (length, AC count, references)."
        ),
        entity="project",
        check_code_prefix="quality_consistency",
    ),
    HeuristicSpec(
        id="v_sequence_drift",
        label="Sequence drift",
        description=(
            "Issue ``sequence`` fields are out of order vs declared "
            "dependencies; auto-fix available."
        ),
        entity="project",
        check_code_prefix="sequence_drift",
    ),
)


_BY_ID: dict[str, HeuristicSpec] = {h.id: h for h in _REGISTRY}
_BY_PREFIX: dict[str, HeuristicSpec] = {h.check_code_prefix: h for h in _REGISTRY}


def known_heuristic_ids() -> set[str]:
    """Return the set of registered heuristic ids.

    Used by the workflow spec validator to flag references to unknown
    heuristics in ``workflow.yaml``.
    """
    return set(_BY_ID.keys())


def heuristic_specs() -> tuple[HeuristicSpec, ...]:
    """Return all registered heuristic specs (UI surfaces consume this)."""
    return _REGISTRY


def heuristic_for_check_code(code: str) -> HeuristicSpec | None:
    """Map a validator ``CheckResult.code`` back to its heuristic id.

    Lookup is by the ``"<prefix>/..."`` split — the part before the
    first slash is the canonical detector id.
    """
    prefix = code.split("/", 1)[0] if "/" in code else code
    return _BY_PREFIX.get(prefix)


__all__ = [
    "HeuristicSpec",
    "gc_markers",
    "has_marker",
    "heuristic_for_check_code",
    "heuristic_specs",
    "known_heuristic_ids",
    "marker_path",
    "reset_markers",
    "write_marker",
]
