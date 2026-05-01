"""Drift report — single coherence score (KUI-128 / A3).

Aggregates the project's existing drift signals into one 0-100
score. Higher is healthier. The signals are:

- ``stale_pins`` — pinned references whose target has had a
  PM-marked contract change. Heavy weight.
- ``unresolved_refs`` — `[[id]]` references that don't resolve to
  any known entity. Heavy weight.
- ``stale_concepts`` — concept nodes whose `source.content_hash`
  no longer matches the file on disk. Medium weight.
- ``workflow_drift_findings`` — active mismatches between declared
  ``workflow.yaml`` stations and the canonical v0.9 workflow event log.
  Medium weight. Reads ``events/*.jsonl`` via the KUI-123 substrate.

Weights are starting values, calibrated by inspection rather than a
data-driven study. ``decisions.md`` documents this; the PM can
recalibrate against the v0 PT corpus by adjusting :data:`WEIGHTS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tripwire.core.validator import load_context, validate_project
from tripwire.core.workflow.drift import DriftFinding, detect_drift
from tripwire.core.workflow.loader import load_workflows

# Penalty per occurrence (point loss). The cap prevents one type of
# drift from monopolising the headline score.
WEIGHTS: dict[str, dict[str, int]] = {
    "stale_pins": {"per": 5, "cap": 50},
    "unresolved_refs": {"per": 5, "cap": 50},
    "stale_concepts": {"per": 2, "cap": 20},
    "workflow_drift_findings": {"per": 2, "cap": 20},
}


@dataclass
class CoherenceReport:
    score: int
    breakdown: dict[str, int]
    workflow_drift_findings: list[DriftFinding]


def compute_coherence(project_dir: Path) -> CoherenceReport:
    """Compute the coherence score for `project_dir`.

    Returns the integer score and a breakdown dict keyed by signal
    name with the raw count for each.
    """
    breakdown: dict[str, int] = {
        "stale_pins": 0,
        "unresolved_refs": 0,
        "stale_concepts": 0,
        "workflow_drift_findings": 0,
    }

    # Run the validator to harvest two of the four signals at once:
    # references/dangling (unresolved refs) and references/stale_pin
    # (stale pins). The validator already does this analysis; the
    # drift report just rolls up the counts.
    try:
        report = validate_project(project_dir, strict=False, fix=False)
    except Exception:
        # Validator failure shouldn't fail drift reporting outright.
        report = None

    if report is not None:
        for finding in [*report.errors, *report.warnings]:
            code = finding.code
            if code == "references/stale_pin":
                breakdown["stale_pins"] += 1
            elif code == "ref/dangling":
                breakdown["unresolved_refs"] += 1

    # Stale concepts: walk concept-node freshness directly. The cache
    # tracks `source.content_hash` per node; the validator's freshness
    # check already classifies as STALE / FRESH / NO_SOURCE etc.
    breakdown["stale_concepts"] = _count_stale_concepts(project_dir)

    # Workflow drift: compare declared workflows with the canonical v0.9
    # append-only event log. Missing workflow.yaml or unreadable workflow
    # declarations yield no workflow-drift findings; the other signals still
    # report normally.
    workflow_drift_findings = _collect_workflow_drift_findings(project_dir)
    breakdown["workflow_drift_findings"] = len(workflow_drift_findings)

    score = 100
    for name, count in breakdown.items():
        weight = WEIGHTS.get(name)
        if weight is None or count == 0:
            continue
        penalty = min(count * weight["per"], weight["cap"])
        score -= penalty
    score = max(0, score)

    return CoherenceReport(
        score=score,
        breakdown=breakdown,
        workflow_drift_findings=workflow_drift_findings,
    )


def _count_stale_concepts(project_dir: Path) -> int:
    """Best-effort count of stale concept nodes via freshness checking."""
    try:
        from tripwire.core.freshness import compute_freshness
        from tripwire.models.graph import FreshnessStatus
    except ImportError:
        return 0

    try:
        ctx = load_context(project_dir)
    except Exception:
        return 0

    count = 0
    for entity in ctx.nodes:
        node = entity.model
        if node.source is None or not node.source.content_hash:
            continue
        try:
            result = compute_freshness(project_dir, node)
        except Exception:
            continue
        if result.status == FreshnessStatus.STALE:
            count += 1
    return count


def _collect_workflow_drift_findings(project_dir: Path) -> list[DriftFinding]:
    """Return workflow-drift findings for every declared workflow."""
    try:
        spec = load_workflows(project_dir)
    except Exception:
        return []

    findings: list[DriftFinding] = []
    for workflow_id in spec.workflows:
        try:
            findings.extend(detect_drift(project_dir, workflow_id=workflow_id))
        except Exception:
            continue
    return findings


def drift_finding_to_dict(finding: DriftFinding) -> dict[str, str | None]:
    """Serialize a workflow drift finding for CLI/API JSON payloads."""
    return {
        "code": finding.code,
        "workflow": finding.workflow,
        "instance": finding.instance,
        "station": finding.station,
        "severity": finding.severity,
        "message": finding.message,
    }


__all__ = [
    "WEIGHTS",
    "CoherenceReport",
    "compute_coherence",
    "drift_finding_to_dict",
]
