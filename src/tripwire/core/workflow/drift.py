"""Workflow drift detection (KUI-124).

Drift is the gap between the workflow.yaml-declared lifecycle and what
the events log records actually happened. Three classes of drift:

- ``drift/prompt_check_missing`` — a station declared
  ``prompt_checks: [...]`` but the session left the station without a
  ``prompt_check.invoked`` event for one of the declared ids. The PM
  forgot to run a required check.
- ``drift/tripwire_should_have_fired`` — a station declared
  ``tripwires: [...]`` but the session left without a
  ``tripwire.fired`` event for one of them. Either the tripwire is
  miswired or the gate runner skipped it.
- ``drift/unexpected_transition`` — session.yaml currently sits at a
  station that's NOT reachable from the last
  ``transition.completed.to_station``. Means somebody (or some tool)
  flipped session.status directly without going through
  ``tripwire transition``.

Surfaced via :func:`detect_drift` (returns
:class:`DriftFinding` list) and the ``tripwire drift report`` CLI.

The reader walks the events log chronologically, partitions events by
station-stay (each ``transition.completed`` ends one stay), and for
each completed stay checks the declared prompt-checks/tripwires.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from tripwire.core.events.log import read_events
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.schema import NextSpec, Workflow


@dataclass(frozen=True)
class DriftFinding:
    """One drift between declared workflow and observed events."""

    code: str
    workflow: str
    instance: str
    station: str | None
    message: str
    severity: Literal["error", "warning"] = "error"


def detect_drift(
    project_dir: Path,
    *,
    instance: str | None = None,
    workflow_id: str = "coding-session",
) -> list[DriftFinding]:
    """Walk the events log, return all detected drift findings.

    Filters by ``instance`` when supplied — useful for narrowing to one
    session at a time. ``workflow_id`` defaults to ``coding-session``;
    other workflows piggyback once they're declared in workflow.yaml.
    """
    spec = load_workflows(project_dir)
    workflow = spec.workflows.get(workflow_id)
    if workflow is None:
        return []

    rows = list(read_events(project_dir, workflow=workflow_id, instance=instance))
    findings: list[DriftFinding] = []
    findings.extend(_scan_stay_drift(rows, workflow))
    findings.extend(_scan_unexpected_transitions(project_dir, rows, workflow))
    return findings


def _scan_stay_drift(rows: list[dict], workflow: Workflow) -> list[DriftFinding]:
    """For each `transition.completed` row, look at the FROM station's
    declared prompt-checks + tripwires and confirm one of each was
    observed during the stay.

    A "stay" is the contiguous run of events on a session at a given
    station, ending in `transition.completed.from_station == <station>`.
    The opening boundary is either the previous `transition.completed`
    (same instance) or the start of the events log.
    """
    out: list[DriftFinding] = []
    by_instance: dict[str, list[dict]] = {}
    for row in rows:
        inst = row.get("instance") or ""
        by_instance.setdefault(inst, []).append(row)

    stations_by_id = workflow.stations_by_id
    for inst, inst_rows in by_instance.items():
        stay_start = 0
        for idx, row in enumerate(inst_rows):
            if row.get("event") != "transition.completed":
                continue
            details = row.get("details") or {}
            from_station = details.get("from_station")
            if not isinstance(from_station, str):
                continue
            station = stations_by_id.get(from_station)
            if station is None:
                continue
            stay_rows = inst_rows[stay_start:idx]
            invoked_pcs = _ids_for_event(stay_rows, "prompt_check.invoked")
            fired_tws = _ids_for_event(stay_rows, "tripwire.fired")
            for pc in station.prompt_checks:
                if pc not in invoked_pcs:
                    out.append(
                        DriftFinding(
                            code="drift/prompt_check_missing",
                            workflow=workflow.id,
                            instance=inst,
                            station=from_station,
                            message=(
                                f"session {inst!r} left station "
                                f"{from_station!r} without invoking required "
                                f"prompt-check {pc!r}"
                            ),
                        )
                    )
            for tw in station.tripwires:
                if tw not in fired_tws:
                    out.append(
                        DriftFinding(
                            code="drift/tripwire_should_have_fired",
                            workflow=workflow.id,
                            instance=inst,
                            station=from_station,
                            message=(
                                f"session {inst!r} left station "
                                f"{from_station!r} without firing declared "
                                f"tripwire {tw!r}"
                            ),
                        )
                    )
            stay_start = idx + 1
    return out


def _ids_for_event(rows: Iterable[dict], event: str) -> set[str]:
    """Extract ``details.id`` values for rows matching ``event``."""
    out: set[str] = set()
    for row in rows:
        if row.get("event") != event:
            continue
        details = row.get("details") or {}
        ident = details.get("id")
        if isinstance(ident, str):
            out.add(ident)
    return out


def _scan_unexpected_transitions(
    project_dir: Path, rows: list[dict], workflow: Workflow
) -> list[DriftFinding]:
    """Compare session.yaml's current status against the last
    `transition.completed.to_station` from the events log. If the
    session sits at a station NOT reachable from the last logged stop,
    surface `drift/unexpected_transition` — somebody flipped status
    directly.

    Sessions whose YAML is missing or unreadable are skipped silently
    (they're orphaned event rows; not a drift in the
    declared-vs-observed sense).
    """
    out: list[DriftFinding] = []
    last_to_by_instance: dict[str, str] = {}
    for row in rows:
        if row.get("event") != "transition.completed":
            continue
        details = row.get("details") or {}
        to_station = details.get("to_station")
        inst = row.get("instance") or ""
        if isinstance(to_station, str) and inst:
            last_to_by_instance[inst] = to_station

    for inst, last_to in last_to_by_instance.items():
        actual = _read_session_status(project_dir, inst)
        if actual is None:
            continue  # session.yaml missing — orphan, not drift
        if actual == last_to:
            continue  # in sync
        # Reachable-from-last-stop?
        last_station = workflow.stations_by_id.get(last_to)
        if last_station is None:
            continue
        if _is_reachable_via(last_station.next, actual):
            continue  # legitimate single-step move; the gate just hasn't
            # logged a `transition.completed` for it yet.
        out.append(
            DriftFinding(
                code="drift/unexpected_transition",
                workflow=workflow.id,
                instance=inst,
                station=actual,
                message=(
                    f"session {inst!r} session.yaml status={actual!r} but "
                    f"last logged transition.completed was to "
                    f"{last_to!r}, and {actual!r} is not reachable from "
                    f"{last_to!r} via workflow.yaml's `next:` declaration "
                    f"— suggests a gate-bypass status flip"
                ),
            )
        )
    return out


def _is_reachable_via(spec: NextSpec, target: str) -> bool:
    if spec.kind == "single":
        return spec.single == target
    if spec.kind == "conditional" and spec.conditional is not None:
        return any(b.then == target for b in spec.conditional)
    return False


def _read_session_status(project_dir: Path, instance: str) -> str | None:
    """Best-effort read of ``sessions/<instance>/session.yaml`` status."""
    try:
        from tripwire.core.session_store import load_session
    except ImportError:  # pragma: no cover — defensive
        return None
    try:
        session = load_session(project_dir, instance)
    except (FileNotFoundError, OSError):
        return None
    except Exception:
        return None
    return session.status.value


__all__ = ["DriftFinding", "detect_drift"]
