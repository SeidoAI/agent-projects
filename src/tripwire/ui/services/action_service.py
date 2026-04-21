"""Global-action service — validate, rebuild-index, phase advance, finalize.

Every destructive UI action flows through here so the HTTP routes stay
thin: parse the request, call one function on this module, emit any
WebSocket event, return the result DTO. The service layer owns:

- the validator subprocess (via :func:`tripwire.core.validator.validate_project`,
  run on a background thread by the route);
- the graph-cache rebuild (via
  :func:`tripwire.core.graph_cache.ensure_fresh`);
- the phase-advance transaction — write `phase`, validate, revert on
  failure — with an `flock`-held ``project.yaml`` to avoid racing
  `tripwire next-key` or another advance_phase;
- the session finalisation — flip status to ``completed``, stamp
  ``updated_at``, and close any open engagements.

Every successful mutation writes a JSON-line audit entry via
:mod:`tripwire.ui.services._audit`. The existing
``POST /api/actions/validate`` route delegates here (see
:mod:`tripwire.ui.routes.actions`); its WebSocket emission stays in the
route because it's tied to ``request.app.state.event_queue``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tripwire.core import graph_cache
from tripwire.core.locks import project_lock
from tripwire.core.session_store import load_session, save_session
from tripwire.core.store import load_project, save_project
from tripwire.core.validator import ValidationReport, validate_project
from tripwire.models.project import ProjectPhase
from tripwire.ui.services._audit import write_audit_entry

logger = logging.getLogger("tripwire.ui.services.action_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class RebuildResult(BaseModel):
    """Return shape of :func:`rebuild_index`."""

    model_config = ConfigDict(populate_by_name=True)

    cache_rebuilt: bool
    duration_ms: int


class PhaseResult(BaseModel):
    """Return shape of :func:`advance_phase`.

    ``success`` is ``False`` when the post-write ``validate_project`` call
    surfaced errors — in that case ``validation_errors`` carries each
    finding's ``message``, and the phase on disk has been reverted to
    ``from_phase``.
    """

    model_config = ConfigDict(populate_by_name=True)

    from_phase: str
    to_phase: str
    success: bool
    validation_errors: list[str] = []


class SessionResult(BaseModel):
    """Return shape of :func:`finalize_session`."""

    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    status: str
    changed_at: datetime


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_all(project_dir: Path, *, strict: bool = True) -> ValidationReport:
    """Run the full validation gate.

    Thin wrapper around
    :func:`tripwire.core.validator.validate_project` — we want the route
    to go through the service so future cross-cutting concerns (audit
    log, metrics, per-project locks) land here in one place.
    ``validate_project`` runs synchronously and is CPU/IO-bound; the
    route offloads to ``asyncio.to_thread`` so the event loop stays free.
    """
    logger.info("action_service.validate_all: project_dir=%s strict=%s",
                project_dir, strict)
    return validate_project(project_dir, strict=strict)


def rebuild_index(project_dir: Path) -> RebuildResult:
    """Refresh ``graph/index.yaml`` and report whether anything changed.

    ``ensure_fresh`` decides between a full rebuild (missing / corrupt
    cache) and an incremental update (mtime drift). We measure wall time
    from the service layer so the duration matches what the UI sees,
    rather than reaching into the cache module's internal timing.
    """
    started = time.monotonic()
    rebuilt = graph_cache.ensure_fresh(project_dir)
    duration_ms = int((time.monotonic() - started) * 1000)

    write_audit_entry(
        project_dir,
        "actions.rebuild_index",
        before={},
        after={"cache_rebuilt": rebuilt},
        result_summary=f"cache_rebuilt={rebuilt} duration_ms={duration_ms}",
    )
    logger.info(
        "action_service.rebuild_index: rebuilt=%s duration_ms=%d",
        rebuilt, duration_ms,
    )
    return RebuildResult(cache_rebuilt=rebuilt, duration_ms=duration_ms)


def _is_valid_phase(phase: str) -> bool:
    return phase in {p.value for p in ProjectPhase}


def advance_phase(project_dir: Path, new_phase: str) -> PhaseResult:
    """Advance `project.yaml.phase` to *new_phase* with validation gating.

    Steps:

    1. Acquire the project lock so a concurrent ``tripwire next-key`` or
       another advance_phase can't clobber our write.
    2. Load the :class:`ProjectConfig`, snapshot the current phase.
    3. Write `phase: new_phase` while preserving every other field.
    4. Run ``validate_project(strict=True)``.
    5. If validation fails → rewrite the old phase (revert) and return
       ``PhaseResult(success=False, validation_errors=[...])``.

    A try/finally guards the revert so a crash inside ``validate_project``
    doesn't leave a half-advanced phase on disk.

    Raises:
        ValueError: if *new_phase* is not a known :class:`ProjectPhase`
            value — validation would reject it anyway, but the service
            rejects earlier for a cleaner 400 vs 409.
    """
    if not _is_valid_phase(new_phase):
        raise ValueError(
            f"Unknown phase {new_phase!r}. "
            f"Allowed: {sorted(p.value for p in ProjectPhase)}"
        )

    with project_lock(project_dir):
        config = load_project(project_dir)
        old_phase = config.phase.value

        if old_phase == new_phase:
            # Re-validating the same phase is harmless; don't pretend
            # we advanced something we didn't.
            return PhaseResult(
                from_phase=old_phase,
                to_phase=new_phase,
                success=True,
                validation_errors=[],
            )

        config.phase = ProjectPhase(new_phase)
        save_project(project_dir, config)

        try:
            report = validate_project(project_dir, strict=True)
        except BaseException:
            # Revert on any runtime failure so we never leave a
            # half-advanced phase on disk.
            reverted = load_project(project_dir)
            reverted.phase = ProjectPhase(old_phase)
            save_project(project_dir, reverted)
            raise

        if report.errors:
            reverted = load_project(project_dir)
            reverted.phase = ProjectPhase(old_phase)
            save_project(project_dir, reverted)
            errors = [e.message for e in report.errors]
            write_audit_entry(
                project_dir,
                "actions.advance_phase.reverted",
                before={"phase": old_phase},
                after={"phase": old_phase},
                result_summary=(
                    f"{old_phase} → {new_phase} reverted ({len(errors)} errors)"
                ),
                extras={"attempted_phase": new_phase, "errors": errors},
            )
            logger.info(
                "advance_phase: %s → %s reverted (%d errors)",
                old_phase, new_phase, len(errors),
            )
            return PhaseResult(
                from_phase=old_phase,
                to_phase=new_phase,
                success=False,
                validation_errors=errors,
            )

    # Success path — the lock has been released by now; the audit write
    # doesn't need to be inside the critical section.
    write_audit_entry(
        project_dir,
        "actions.advance_phase",
        before={"phase": old_phase},
        after={"phase": new_phase},
        result_summary=f"phase {old_phase} → {new_phase}",
    )
    logger.info("advance_phase: %s → %s OK", old_phase, new_phase)
    return PhaseResult(
        from_phase=old_phase,
        to_phase=new_phase,
        success=True,
        validation_errors=[],
    )


def finalize_session(project_dir: Path, session_id: str) -> SessionResult:
    """Mark a session as ``completed`` and stamp ``updated_at``.

    Any engagement entry that has no ``ended_at`` timestamp is closed
    out with the current time. This matches the verification checklist
    ("status + engagements[].ended_at"). No container operations are
    triggered — v1 finalisation is purely a bookkeeping write.

    Raises:
        FileNotFoundError: if the session yaml is missing (propagated
            from :func:`tripwire.core.session_store.load_session`).
    """
    session = load_session(project_dir, session_id)
    now = datetime.now()
    old_status = session.status
    session.status = "completed"
    session.updated_at = now
    closed_engagements = 0
    for engagement in session.engagements:
        if engagement.ended_at is None:
            engagement.ended_at = now
            closed_engagements += 1
    save_session(project_dir, session)

    write_audit_entry(
        project_dir,
        "actions.finalize_session",
        before={"status": old_status},
        after={"status": "completed", "closed_engagements": closed_engagements},
        result_summary=(
            f"{session_id}: {old_status} → completed "
            f"(closed {closed_engagements} open engagement(s))"
        ),
        extras={"session_id": session_id},
    )
    logger.info(
        "finalize_session: %s %s → completed (%d engagement(s) closed)",
        session_id, old_status, closed_engagements,
    )
    return SessionResult(
        session_id=session_id,
        status="completed",
        changed_at=now,
    )


__all__ = [
    "PhaseResult",
    "RebuildResult",
    "SessionResult",
    "advance_phase",
    "finalize_session",
    "rebuild_index",
    "validate_all",
]
