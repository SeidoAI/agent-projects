"""Global action routes (KUI-34) — validate, rebuild-index, advance-phase,
finalize-session.

Four POST endpoints under ``/api/actions`` that take the project id in
the request body (rather than a path parameter) because these are
global, not project-scoped. Unknown project ids → 404 envelope.

The ``/validate`` body keeps its existing shape — a
:class:`ValidationCompletedEvent` dict — because the WebSocket broadcast
tests assert on it (see ``tests/ui/ws/test_ws_route.py``). The three new
endpoints return their respective service DTOs:
:class:`RebuildResult`, :class:`PhaseResult`, :class:`SessionResult`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel

from tripwire.ui.events import ValidationCompletedEvent
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.action_service import (
    PhaseResult,
    RebuildResult,
    SessionResult,
)
from tripwire.ui.services.project_service import get_project_dir

logger = logging.getLogger("tripwire.ui.routes.actions")

router = APIRouter(prefix="/api/actions", tags=["actions"])


def _resolve_project(project_id: str) -> Path:
    project_dir = get_project_dir(project_id)
    if project_dir is None:
        raise envelope_exception(
            404,
            code="project/not_found",
            detail=f"Project {project_id!r} not found.",
        )
    return project_dir


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class ValidateRequest(BaseModel):
    project_id: str


class RebuildRequest(BaseModel):
    project_id: str


class AdvancePhaseRequest(BaseModel):
    project_id: str
    new_phase: str


class FinalizeSessionRequest(BaseModel):
    project_id: str
    session_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/validate")
async def validate(body: ValidateRequest, request: Request) -> dict:
    """Run the validation gate via the action service and broadcast the result.

    The validator is CPU/IO-bound and synchronous, so the service call
    runs on the default thread pool via :func:`asyncio.to_thread`. The
    emitted event carries real ``errors``/``warnings`` counts and
    ``duration_ms`` from the report.

    Response body is the event shape (``{type, project_id, errors,
    warnings, duration_ms, at?}``) — WebSocket and HTTP consumers get
    identical payloads so they can share a deserialiser.
    """
    # Lazy import — ``tripwire.core.validator`` transitively imports a
    # chunk of the core; we don't want to pay that cost on route
    # registration for apps that never run a validate.
    from tripwire.ui.services.action_service import validate_all

    project_dir = _resolve_project(body.project_id)

    report = await asyncio.to_thread(validate_all, project_dir, strict=True)

    event = ValidationCompletedEvent(
        project_id=body.project_id,
        errors=len(report.errors),
        warnings=len(report.warnings),
        duration_ms=report.duration_ms,
    )
    queue: asyncio.Queue = request.app.state.event_queue
    await queue.put(event)
    return event.to_json()


@router.post("/rebuild-index", response_model=RebuildResult)
async def rebuild_index(body: RebuildRequest) -> RebuildResult:
    from tripwire.ui.services.action_service import rebuild_index as svc

    project_dir = _resolve_project(body.project_id)
    return await asyncio.to_thread(svc, project_dir)


@router.post("/advance-phase", response_model=PhaseResult)
async def advance_phase(body: AdvancePhaseRequest, response: Response) -> PhaseResult:
    """Advance the project phase; return 409 when validation reverted.

    The service returns ``PhaseResult(success=False, validation_errors=[...])``
    on a reverted transition — we flip the response status code to 409
    so the UI's React Query layer sees a retryable failure without
    losing the body (`validation_errors` is still serialised).
    """
    from tripwire.ui.services.action_service import advance_phase as svc

    project_dir = _resolve_project(body.project_id)
    try:
        result = await asyncio.to_thread(svc, project_dir, body.new_phase)
    except ValueError as exc:
        raise envelope_exception(
            400,
            code="phase/invalid",
            detail=str(exc),
        ) from exc

    if not result.success:
        response.status_code = 409
    return result


@router.post("/finalize-session", response_model=SessionResult)
async def finalize_session(body: FinalizeSessionRequest) -> SessionResult:
    from tripwire.ui.services.action_service import finalize_session as svc

    project_dir = _resolve_project(body.project_id)
    try:
        return await asyncio.to_thread(svc, project_dir, body.session_id)
    except FileNotFoundError as exc:
        raise envelope_exception(
            404,
            code="session/not_found",
            detail=f"Session {body.session_id!r} not found in this project.",
        ) from exc
