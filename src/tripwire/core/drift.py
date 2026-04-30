"""Drift report — single coherence score (KUI-128 / A3).

Aggregates the project's existing drift signals into one 0-100
score. Higher is healthier. The signals are:

- ``stale_pins`` — pinned references whose target has had a
  PM-marked contract change. Heavy weight.
- ``unresolved_refs`` — `[[id]]` references that don't resolve to
  any known entity. Heavy weight.
- ``stale_concepts`` — concept nodes whose `source.content_hash`
  no longer matches the file on disk. Medium weight.
- ``workflow_drift_events`` — events tagged ``workflow_drift`` in
  the events log over the prior 7 days. Medium weight. Reads
  ``.tripwire/events.log`` (KUI-123 substrate from
  ``v09-workflow-substrate``); silently 0 if the log is absent.

Weights are starting values, calibrated by inspection rather than a
data-driven study. ``decisions.md`` documents this; the PM can
recalibrate against the v0 PT corpus by adjusting :data:`WEIGHTS`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from tripwire.core.graph import refs as graph_refs
from tripwire.core.validator import load_context, validate_project

# Penalty per occurrence (point loss). The cap prevents one type of
# drift from monopolising the headline score.
WEIGHTS: dict[str, dict[str, int]] = {
    "stale_pins": {"per": 5, "cap": 50},
    "unresolved_refs": {"per": 5, "cap": 50},
    "stale_concepts": {"per": 2, "cap": 20},
    "workflow_drift_events": {"per": 2, "cap": 20},
}

EVENTS_LOG_REL = ".tripwire/events.log"
WORKFLOW_DRIFT_WINDOW_DAYS = 7


@dataclass
class CoherenceReport:
    score: int
    breakdown: dict[str, int]


def compute_coherence(project_dir: Path) -> CoherenceReport:
    """Compute the coherence score for `project_dir`.

    Returns the integer score and a breakdown dict keyed by signal
    name with the raw count for each.
    """
    breakdown: dict[str, int] = {
        "stale_pins": 0,
        "unresolved_refs": 0,
        "stale_concepts": 0,
        "workflow_drift_events": 0,
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

    # Workflow-drift events: optional, depends on KUI-123 substrate.
    breakdown["workflow_drift_events"] = _count_workflow_drift_events(project_dir)

    score = 100
    for name, count in breakdown.items():
        weight = WEIGHTS.get(name)
        if weight is None or count == 0:
            continue
        penalty = min(count * weight["per"], weight["cap"])
        score -= penalty
    score = max(0, score)

    return CoherenceReport(score=score, breakdown=breakdown)


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


def _count_workflow_drift_events(project_dir: Path) -> int:
    """Count `workflow_drift` events in the events log (last 7d)."""
    log_path = project_dir / EVENTS_LOG_REL
    if not log_path.is_file():
        return 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=WORKFLOW_DRIFT_WINDOW_DAYS)

    count = 0
    try:
        with log_path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record: Any = yaml.safe_load(line)
                except yaml.YAMLError:
                    continue
                if not isinstance(record, dict):
                    continue
                if record.get("event") != "workflow_drift":
                    continue
                ts = record.get("at")
                if isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    except ValueError:
                        continue
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt < cutoff:
                        continue
                count += 1
    except OSError:
        return 0
    return count


__all__ = [
    "WEIGHTS",
    "CoherenceReport",
    "compute_coherence",
]


# Suppress an unused import warning — graph_refs is imported because
# `compute_coherence` may dispatch to it in a future iteration when
# the report breaks down per-edge-kind drift; keeping the import
# silent for now keeps the module small.
_ = graph_refs
