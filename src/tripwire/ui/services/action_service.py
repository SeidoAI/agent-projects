"""Global-action service — validate, rebuild-index, phase advance, finalize.

Every destructive UI action flows through here so the HTTP routes stay
thin: parse the request, call one function on this module, emit any
WebSocket event, return the result DTO. The service layer owns:

- the validator subprocess (via :func:`tripwire.core.validator.validate_project`,
  run on a background thread by the route);
- the graph-cache rebuild (via
  :func:`tripwire.core.graph.cache.ensure_fresh`);
- the phase-advance transaction — write `phase`, validate, revert on
  failure — with an `flock`-held ``project.yaml`` to avoid racing
  `tripwire next-key` or another advance_phase;
- the session finalisation — delegate to the same close-out gates used by
  ``tripwire session complete``.

Every successful mutation writes a JSON-line audit entry via
:mod:`tripwire.ui.services._audit`. The existing
``POST /api/actions/validate`` route delegates here (see
:mod:`tripwire.ui.routes.actions`); its WebSocket emission stays in the
route because it's tied to ``request.app.state.event_queue``.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tripwire.core import paths
from tripwire.core.graph import cache as graph_cache
from tripwire.core.locks import project_lock
from tripwire.core.parser import serialize_frontmatter_body
from tripwire.core.session_complete import CompleteError, complete_session
from tripwire.core.session_store import load_session
from tripwire.core.store import load_project
from tripwire.core.validator import ValidationReport, validate_project
from tripwire.models.enums import SessionStatus
from tripwire.models.project import ProjectConfig, ProjectPhase
from tripwire.models.session import AgentSession
from tripwire.ui.services._atomic_write import atomic_write_text, atomic_write_yaml
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


class SessionStatusError(ValueError):
    """Raised when a session is not in the right status for a transition."""


class SessionRuntimeError(RuntimeError):
    """Raised when the runtime refuses to honour a state change (e.g. SIGTERM ignored)."""


class SessionCompletionError(ValueError):
    """Raised when real session close-out gates refuse finalisation."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


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
    logger.info(
        "action_service.validate_all: project_dir=%s strict=%s", project_dir, strict
    )
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
        rebuilt,
        duration_ms,
    )
    return RebuildResult(cache_rebuilt=rebuilt, duration_ms=duration_ms)


def _is_valid_phase(phase: str) -> bool:
    return phase in {p.value for p in ProjectPhase}


def _atomic_save_project(project_dir: Path, config: ProjectConfig) -> None:
    """Atomic replacement for :func:`tripwire.core.store.save_project`.

    The core helper writes ``project.yaml`` via plain ``path.write_text``,
    which the file watcher can observe mid-write as a torn read. Every
    service-layer write of ``project.yaml`` routes through this helper
    so the watcher sees either the old file or the complete new one.
    """
    path = paths.project_config_path(project_dir)
    data = config.model_dump(mode="json", exclude_none=True)
    atomic_write_yaml(path, data)


def _atomic_save_session(project_dir: Path, session: AgentSession) -> None:
    """Atomic replacement for :func:`tripwire.core.session_store.save_session`.

    Same motivation as :func:`_atomic_save_project` — routes the existing
    frontmatter+body serialisation through a tmp-file + ``os.replace``
    so the watcher never observes a torn ``session.yaml``.
    """
    if session.updated_at is None:
        session.updated_at = datetime.now(tz=timezone.utc)
    path = paths.session_yaml_path(project_dir, session.id)
    data = session.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    text = serialize_frontmatter_body(data, session.body)
    atomic_write_text(path, text)


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
        _atomic_save_project(project_dir, config)

        try:
            report = validate_project(project_dir, strict=True)
        except BaseException:
            # Revert using the in-memory snapshot — never re-read the
            # file we just wrote. If that write was partial we'd mask
            # the original error with a garbled load.
            config.phase = ProjectPhase(old_phase)
            _atomic_save_project(project_dir, config)
            raise

        if report.errors:
            # Revert from the same in-memory snapshot.
            config.phase = ProjectPhase(old_phase)
            _atomic_save_project(project_dir, config)
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
                old_phase,
                new_phase,
                len(errors),
            )
            return PhaseResult(
                from_phase=old_phase,
                to_phase=new_phase,
                success=False,
                validation_errors=errors,
            )

        # Success path — audit inside the lock so a crash between save
        # and audit can't leave phase-advanced-but-unaudited state.
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


def pause_session(project_dir: Path, session_id: str) -> SessionResult:
    """Pause an executing session via its runtime; mirrors `tripwire session pause`.

    Behaviour parallels :func:`tripwire.cli.session.session_pause_cmd` so the
    INTERVENE button and the CLI converge on the same status guarantees:

    - status must be ``executing``; otherwise :class:`SessionStatusError`
    - if the session's PID is non-null but no longer alive, the runtime
      already exited; status flips to ``failed`` (not ``paused``) so we
      don't lie about the reality on disk.
    - otherwise, ``runtime.pause(session)`` is invoked. A
      :class:`RuntimeError` from the runtime (e.g. SIGTERM ignored within
      the 2-second window) leaves status as ``executing`` and surfaces
      as :class:`SessionRuntimeError` for the caller to translate.

    Raises:
        FileNotFoundError: session yaml missing.
        SessionStatusError: session not in ``executing`` state.
        SessionRuntimeError: runtime refused to pause cleanly.
    """
    from tripwire.core.process_helpers import is_alive
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    with project_lock(project_dir):
        session = load_session(project_dir, session_id)
        old_status = session.status
        if old_status != "executing":
            raise SessionStatusError(
                f"session {session_id!r} is {old_status!r}, must be 'executing' to pause"
            )

        spawn = load_resolved_spawn_config(project_dir, session=session)
        runtime = get_runtime(spawn.invocation.runtime)

        now = datetime.now(tz=timezone.utc)
        pid = session.runtime_state.pid
        if pid and not is_alive(pid):
            session.status = SessionStatus.FAILED
            session.updated_at = now
            _atomic_save_session(project_dir, session)
            write_audit_entry(
                project_dir,
                "actions.pause_session",
                before={"status": old_status},
                after={"status": "failed"},
                result_summary=f"{session_id}: pid {pid} not alive → failed",
                extras={"session_id": session_id, "reason": "dead_pid"},
            )
            logger.info(
                "pause_session: %s pid %d not alive — flipped to failed",
                session_id,
                pid,
            )
            return SessionResult(session_id=session_id, status="failed", changed_at=now)

        try:
            runtime.pause(session)
        except RuntimeError as exc:
            raise SessionRuntimeError(str(exc)) from exc

        session.status = SessionStatus.PAUSED
        session.updated_at = now
        _atomic_save_session(project_dir, session)
        write_audit_entry(
            project_dir,
            "actions.pause_session",
            before={"status": old_status},
            after={"status": "paused"},
            result_summary=f"{session_id}: {old_status} → paused",
            extras={"session_id": session_id},
        )
    logger.info("pause_session: %s %s → paused", session_id, old_status)
    return SessionResult(session_id=session_id, status="paused", changed_at=now)


def finalize_session(project_dir: Path, session_id: str) -> SessionResult:
    """Run the canonical session-complete close-out and return status.

    The UI route must not be a second completion path. It delegates to
    :func:`tripwire.core.session_complete.complete_session`, which enforces
    the same status, merged-PR, required-artifact, and review gates as the
    CLI. A refused gate becomes :class:`SessionCompletionError` for routes
    to translate into a 409 envelope.

    Raises:
        FileNotFoundError: if the session yaml is missing (propagated
            from :func:`tripwire.core.session_store.load_session`).
        SessionCompletionError: if a close-out gate refuses completion.
    """
    before = load_session(project_dir, session_id)
    old_status = before.status
    try:
        complete_session(project_dir, session_id)
    except CompleteError as exc:
        raise SessionCompletionError(exc.code, str(exc)) from exc

    session = load_session(project_dir, session_id)
    changed_at = session.updated_at or datetime.now(tz=timezone.utc)
    write_audit_entry(
        project_dir,
        "actions.finalize_session",
        before={"status": old_status},
        after={"status": session.status},
        result_summary=f"{session_id}: {old_status} → {session.status}",
        extras={"session_id": session_id},
    )
    logger.info("finalize_session: %s %s → %s", session_id, old_status, session.status)
    return SessionResult(
        session_id=session_id,
        status=str(session.status),
        changed_at=changed_at,
    )


__all__ = [
    "PhaseResult",
    "RebuildResult",
    "SessionCompletionError",
    "SessionResult",
    "SessionRuntimeError",
    "SessionStatusError",
    "advance_phase",
    "finalize_session",
    "pause_session",
    "rebuild_index",
    "validate_all",
]
