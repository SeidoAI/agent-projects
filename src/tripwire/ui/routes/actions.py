"""Global action routes — validate, rebuild-index, advance-phase, finalize.

Only ``POST /api/actions/validate`` is wired in v1; the others land with
KUI-23. The validate route enqueues a
:class:`~tripwire.ui.events.ValidationCompletedEvent` so the realtime
delivery path (queue → broadcaster → hub → clients) is live.
"""

from __future__ import annotations

import asyncio
import logging
import time

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
    """Run project validation and enqueue a ValidationCompletedEvent.

    The full ``tripwire.core.validator`` wiring lands with KUI-23. Until
    then, this route enqueues a placeholder event (errors=0, warnings=0)
    so every UI surface that listens for ``validation_completed`` is
    already on the live delivery path.
    """
    if get_project_dir(body.project_id) is None:
        raise HTTPException(status_code=404, detail="Project not found")

    start = time.monotonic()
    errors, warnings = 0, 0  # TODO(KUI-23): invoke tripwire.core.validator
    duration_ms = int((time.monotonic() - start) * 1000)

    event = ValidationCompletedEvent(
        project_id=body.project_id,
        errors=errors,
        warnings=warnings,
        duration_ms=duration_ms,
    )
    queue: asyncio.Queue = request.app.state.event_queue
    await queue.put(event)
    return event.to_json()
