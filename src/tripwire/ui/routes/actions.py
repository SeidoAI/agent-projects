"""Global action routes — validate, rebuild-index, advance-phase, finalize.

Only ``POST /api/actions/validate`` is wired in v1; the others land with
KUI-23. The validate route runs ``tripwire.core.validator.validate_project``
and enqueues a :class:`~tripwire.ui.events.ValidationCompletedEvent` so the
realtime delivery path (queue → broadcaster → hub → clients) is live.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tripwire.ui.events import ValidationCompletedEvent
from tripwire.ui.services.project_service import get_project_dir

logger = logging.getLogger("tripwire.ui.routes.actions")

router = APIRouter(prefix="/api/actions", tags=["actions"])


class ValidateRequest(BaseModel):
    project_id: str


@router.post("/validate")
async def validate(body: ValidateRequest, request: Request) -> dict:
    """Run ``validate_project(strict=True)`` and broadcast the result.

    The validator is CPU/IO-bound and synchronous, so it runs on the
    default thread pool via :func:`asyncio.to_thread`. The emitted event
    carries real ``errors``/``warnings`` counts and ``duration_ms`` from
    the report — not placeholder zeros.

    KUI-23 will later move this wiring into a dedicated action service;
    the emission path stays the same.
    """
    # Lazy import — ``tripwire.core.validator`` transitively imports a
    # chunk of the core, and we don't want to pay that cost on route
    # registration for apps that never run a validate.
    from tripwire.core.validator import validate_project

    project_dir = get_project_dir(body.project_id)
    if project_dir is None:
        raise HTTPException(status_code=404, detail="Project not found")

    report = await asyncio.to_thread(validate_project, project_dir, strict=True)

    event = ValidationCompletedEvent(
        project_id=body.project_id,
        errors=len(report.errors),
        warnings=len(report.warnings),
        duration_ms=report.duration_ms,
    )
    queue: asyncio.Queue = request.app.state.event_queue
    await queue.put(event)
    return event.to_json()
