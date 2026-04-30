"""Read-side service for the v0.9 workflow events log.

Wraps :func:`tripwire.core.events.log.read_events` for the UI's
``/api/projects/{pid}/workflow-events`` and ``/workflow-stats``
endpoints. Distinct from
:mod:`tripwire.ui.services.event_aggregator` (the v0.8 emitter, with
its own on-disk layout); the two coexist for the UI rather than the
v0.9 surface ripping out the v0.8 one — the validator/tripwire events
that drive the dashboard still flow through the v0.8 path.

All read-only. Filters are applied here rather than passed to the
underlying generator because the generator pre-filters anyway —
keeping the service-side wrapper lets us add response shaping
(ordering, top-N, kind histograms) without touching core.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tripwire.core.events.log import read_events

DEFAULT_LIMIT = 200
MAX_LIMIT = 1000


@dataclass(frozen=True)
class WorkflowEventsPage:
    """One page of the workflow events list."""

    events: list[dict[str, Any]]
    total: int


@dataclass(frozen=True)
class WorkflowStats:
    """Aggregate analytics over the workflow events log."""

    total: int
    by_kind: dict[str, int] = field(default_factory=dict)
    by_instance: dict[str, int] = field(default_factory=dict)
    top_rules: list[dict[str, Any]] = field(default_factory=list)


def list_workflow_events(
    project_dir: Path,
    *,
    workflow: str | None = None,
    instance: str | None = None,
    station: str | None = None,
    event: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> WorkflowEventsPage:
    """Return a chronologically-ordered (newest-last) page of events.

    The events log is naturally append-only and sorted, so ``limit``
    just truncates the tail. We deliberately preserve forward order
    (oldest → newest) here because the EventLog UI auto-scrolls
    bottom-on-mount and reverse-paginates upward — matching the events
    log's natural shape avoids an O(N) flip on every read.
    """
    rows = list(
        read_events(
            project_dir,
            workflow=workflow,
            instance=instance,
            station=station,
            event=event,
        )
    )
    total = len(rows)
    bounded = max(1, min(limit, MAX_LIMIT))
    if total > bounded:
        rows = rows[-bounded:]
    return WorkflowEventsPage(events=rows, total=total)


def stats(
    project_dir: Path,
    *,
    workflow: str | None = None,
    top_n: int = 10,
) -> WorkflowStats:
    """Aggregate counts over the workflow events log.

    - ``by_kind`` — count of events per ``event`` field
    - ``by_instance`` — count of events per ``instance`` field
    - ``top_rules`` — top N (validator/tripwire/prompt-check) ids by
      fire count, derived from ``details.id`` on each row that has one.
    """
    by_kind: Counter[str] = Counter()
    by_instance: Counter[str] = Counter()
    by_rule: Counter[str] = Counter()
    total = 0
    for row in read_events(project_dir, workflow=workflow):
        total += 1
        kind = row.get("event")
        if isinstance(kind, str):
            by_kind[kind] += 1
        inst = row.get("instance")
        if isinstance(inst, str):
            by_instance[inst] += 1
        details = row.get("details") or {}
        rid = details.get("id")
        if isinstance(rid, str):
            by_rule[rid] += 1

    return WorkflowStats(
        total=total,
        by_kind=dict(by_kind),
        by_instance=dict(by_instance),
        top_rules=[
            {"id": rid, "count": count}
            for rid, count in by_rule.most_common(max(0, top_n))
        ],
    )


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "WorkflowEventsPage",
    "WorkflowStats",
    "list_workflow_events",
    "stats",
]
