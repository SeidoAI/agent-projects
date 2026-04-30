"""Transition-token runtime — the workflow gate runner (KUI-159).

A transition is a request to move a session from its current station
to a target station. The runtime:

1. Loads ``<project>/workflow.yaml``, finds the workflow the session
   belongs to (``coding-session`` for v0.9; future workflows look up
   by ``trigger:`` against the spawn event).
2. Verifies the target station is reachable from the current station
   (single-id ``next:`` matches, or one of the conditional branches
   resolves to it).
3. Runs the gate:

   a. **Validators** — call :func:`tripwire.core.validator.validate_project`
      with ``strict=True``. Any error fails the gate. This is the
      same code path the KUI-110 edit-time hook drives (no parallel
      hook surface).
   b. **Tripwires** — for every tripwire registered at the target
      station (``at = (workflow, station)``), confirm
      :meth:`Tripwire.is_acknowledged` returns True. An unack'd
      blocking tripwire fails the gate.
   c. **Prompt-checks** — for every prompt-check declared at the
      *current* station, query the events log to verify it was
      invoked since the session entered the current station. Missing
      ones fail the gate. (Verifies the PM ran the required check
      before the agent transitioned away.)

4. On pass: session.status = target, ``current_station_instance``
   bumped, ``transition.completed`` emitted.
5. On fail: ``transition.rejected`` emitted with a structured
   ``reason``; session stays put.

Concurrency: per-session lockfile under
``.tripwire/locks/transition-<sid>.lock`` serialises concurrent
transitions on the same session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.events.log import emit_event, read_events
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.session_store import load_session, save_session
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.registry import tripwires_for_station
from tripwire.core.workflow.schema import (
    NextSpec,
    Workflow,
    WorkflowSpec,
)
from tripwire.models.enums import SessionStatus

logger = logging.getLogger(__name__)


WORKFLOW_ID = "coding-session"


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of one transition request."""

    ok: bool
    reason: str | None  # structured reason code; None on pass
    message: str | None  # human-readable detail
    station_instance: str | None  # `{workflow}:{instance}:{station}:{n}` on pass


class TransitionError(Exception):
    """Raised for unrecoverable input errors (unknown session/station)."""


def _isoformat_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_workflow(spec: WorkflowSpec) -> Workflow:
    """Return the canonical workflow for v0.9 — only ``coding-session``
    is materialised. Raises :class:`TransitionError` if missing."""
    wf = spec.workflows.get(WORKFLOW_ID)
    if wf is None:
        raise TransitionError(
            f"workflow {WORKFLOW_ID!r} is not declared in workflow.yaml"
        )
    return wf


def _is_reachable(current: str, target: str, next_spec: NextSpec) -> bool:
    """True iff ``target`` is reachable from ``current`` via ``next_spec``."""
    if next_spec.kind == "single":
        return next_spec.single == target
    if next_spec.kind == "conditional":
        if next_spec.conditional is None:
            return False
        # Equality predicates are evaluated against an empty context
        # for now — the runtime context is built by the gate runner
        # later. We accept any branch whose `then` matches the target
        # since reachability ≠ what-actually-happens-at-runtime.
        return any(branch.then == target for branch in next_spec.conditional)
    return False  # terminal — nothing reachable


def _next_station_instance_n(
    project_dir: Path, workflow: str, instance: str, station: str
) -> int:
    """Count prior `transition.completed` events for this station and
    return n+1, where n is the number of prior visits."""
    n = 0
    for row in read_events(
        project_dir,
        workflow=workflow,
        instance=instance,
        event="transition.completed",
    ):
        details = row.get("details") or {}
        if details.get("to_station") == station:
            n += 1
    return n + 1


def request_transition(
    project_dir: Path,
    *,
    session_id: str,
    target_station: str,
    now: datetime | None = None,
) -> TransitionResult:
    """Run the gate and apply the transition.

    Always emits ``transition.requested`` first, then either
    ``transition.completed`` (pass) or ``transition.rejected`` (fail).
    Raises :class:`TransitionError` for input errors that don't
    correspond to a gate verdict (unknown session / station).
    """
    when = now or datetime.now(tz=timezone.utc)

    spec = load_workflows(project_dir)
    workflow = _resolve_workflow(spec)
    stations_by_id = workflow.stations_by_id
    if target_station not in stations_by_id:
        raise TransitionError(
            f"unknown station {target_station!r} in workflow {WORKFLOW_ID!r}; "
            f"valid stations: {sorted(stations_by_id)}"
        )

    try:
        session = load_session(project_dir, session_id)
    except FileNotFoundError as exc:
        raise TransitionError(f"session {session_id!r} not found") from exc

    current_station = session.status.value
    current = stations_by_id.get(current_station)

    # Always emit `transition.requested` first.
    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        station=target_station,
        event="transition.requested",
        details={"from_station": current_station, "to_station": target_station},
        now=when,
    )

    lock_name = f".tripwire/locks/transition-{session_id}.lock"
    try:
        with project_lock(project_dir, name=lock_name):
            return _run_gate(
                project_dir,
                session=session,
                current=current,
                current_station=current_station,
                target_station=target_station,
                stations_by_id=stations_by_id,
                when=when,
            )
    except LockTimeout as exc:
        result = TransitionResult(
            ok=False,
            reason="lock_timeout",
            message=str(exc),
            station_instance=None,
        )
        emit_event(
            project_dir,
            workflow=WORKFLOW_ID,
            instance=session_id,
            station=target_station,
            event="transition.rejected",
            details={"reason": result.reason, "message": result.message},
            now=datetime.now(tz=timezone.utc),
        )
        return result


def _run_gate(
    project_dir: Path,
    *,
    session,
    current,
    current_station: str,
    target_station: str,
    stations_by_id: dict,
    when: datetime,
) -> TransitionResult:
    """The gate body. Caller holds the per-session transition lock."""
    session_id = session.id
    # 1. Reachability.
    if current is None:
        return _reject(
            project_dir,
            session_id,
            target_station,
            reason=f"transition_not_reachable: current station "
            f"{current_station!r} is not declared in workflow.yaml",
        )
    if not _is_reachable(current_station, target_station, current.next):
        return _reject(
            project_dir,
            session_id,
            target_station,
            reason=f"transition_not_reachable: cannot move from "
            f"{current_station!r} to {target_station!r} via declared `next:`",
        )

    # 2. Validators — KUI-110's edit-time validate_project surface.
    from tripwire.cli.transition import validate_project

    report = validate_project(project_dir, strict=True, fix=False)
    if report.errors:
        first = report.errors[0]
        return _reject(
            project_dir,
            session_id,
            target_station,
            reason=f"validators_failed: {first.code}: {first.message}",
        )

    # 3. Tripwires — every tripwire registered at the target station
    # must be acknowledged. Unack'd blocking tripwires fail the gate.
    tripwire_ids = tripwires_for_station(WORKFLOW_ID, target_station)
    if tripwire_ids:
        from tripwire._internal.tripwires.loader import load_registry

        # The registry indexes by `fires_on` event; we want the
        # subset that registered at this station via class-level `at`.
        registry = load_registry(project_dir)
        unacked = _unacked_station_tripwires(
            project_dir, registry, session_id=session_id, want_ids=set(tripwire_ids)
        )
        if unacked:
            return _reject(
                project_dir,
                session_id,
                target_station,
                reason=f"tripwires_not_acknowledged: {sorted(unacked)}",
            )

    # 4. Required prompt-checks declared on the current station in
    # workflow.yaml must have been invoked since the session entered
    # the current station. We use the workflow.yaml declaration
    # (`current.prompt_checks`), NOT the global registry, so a project
    # can keep prompt-checks defined-but-unrequired without forcing
    # them on every transition.
    required_pcs = list(current.prompt_checks)
    if required_pcs:
        invoked = _invoked_prompt_checks_at_station(
            project_dir, instance=session_id, station=current_station
        )
        missing = [pc for pc in required_pcs if pc not in invoked]
        if missing:
            return _reject(
                project_dir,
                session_id,
                target_station,
                reason=f"prompt_checks_missing: {missing}",
            )

    # 5. Pass — assign station-instance id, save session, emit completed.
    n = _next_station_instance_n(project_dir, WORKFLOW_ID, session_id, target_station)
    station_instance = f"{WORKFLOW_ID}:{session_id}:{target_station}:{n}"
    session.status = SessionStatus(target_station)
    session.current_station_instance = station_instance
    session.updated_at = when
    save_session(project_dir, session)

    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        station=target_station,
        event="transition.completed",
        details={
            "from_station": current_station,
            "to_station": target_station,
            "station_instance": station_instance,
        },
        now=datetime.now(tz=timezone.utc),
    )
    return TransitionResult(
        ok=True,
        reason=None,
        message=None,
        station_instance=station_instance,
    )


def _reject(
    project_dir: Path,
    session_id: str,
    target_station: str,
    *,
    reason: str,
) -> TransitionResult:
    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        station=target_station,
        event="transition.rejected",
        details={"reason": reason},
    )
    return TransitionResult(
        ok=False,
        reason=reason.split(":", 1)[0],
        message=reason,
        station_instance=None,
    )


def _unacked_station_tripwires(
    project_dir: Path,
    registry: dict,
    *,
    session_id: str,
    want_ids: set[str],
) -> set[str]:
    """Return the subset of ``want_ids`` whose tripwire is not
    acknowledged for the session.

    The tripwire registry is keyed by `fires_on` event; we walk it,
    find each instance whose id is in ``want_ids``, build a
    :class:`TripwireContext`, and ask
    :meth:`Tripwire.is_acknowledged`. Missing tripwires (in the want
    set but not loaded) count as unacked — the gate is conservative.
    """
    from tripwire._internal.tripwires import TripwireContext
    from tripwire.core.store import load_project

    project = load_project(project_dir)
    project_id = project.name.lower().replace(" ", "-")
    ctx = TripwireContext(
        project_dir=project_dir, session_id=session_id, project_id=project_id
    )
    unacked = set(want_ids)
    for instances in registry.values():
        for tw in instances:
            if tw.id in unacked and tw.is_acknowledged(ctx):
                unacked.discard(tw.id)
    return unacked


def _invoked_prompt_checks_at_station(
    project_dir: Path, *, instance: str, station: str
) -> set[str]:
    """Return prompt-check ids invoked for ``instance`` at ``station``
    since the session entered the station — derived by walking the
    events log for `prompt_check.invoked` events filtered by
    instance/station."""
    invoked: set[str] = set()
    for row in read_events(
        project_dir,
        instance=instance,
        station=station,
        event="prompt_check.invoked",
    ):
        details = row.get("details") or {}
        pc_id = details.get("id")
        if isinstance(pc_id, str):
            invoked.add(pc_id)
    return invoked


__all__ = [
    "WORKFLOW_ID",
    "TransitionError",
    "TransitionResult",
    "request_transition",
]
