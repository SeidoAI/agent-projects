"""Process-event stream routes (KUI-100).

Two endpoints under ``/api/projects/{project_id}``:

    GET  /events                       paginated list with filters
    GET  /events/{event_id}            full body of one event

Reads from `<project_dir>/.tripwire/events/<kind>/<sid>/<n>.json` via
:mod:`tripwire.ui.services.event_aggregator`. PM-mode redaction is a
no-op here: validator and artifact-rejection events are public; only
tripwire prompts (in `/api/workflow`) need PM-gating.

See `docs/specs/2026-04-26-v08-handoff.md` §2.2-§2.3.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.event_aggregator import (
    DEFAULT_LIMIT,
    EventNotFoundError,
    get_event,
    list_events,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["events"])


@router.get("/events")
async def list_events_route(
    project: ProjectContext = Depends(get_project),  # noqa: B008
    session_id: str | None = Query(None),
    kind: list[str] | None = Query(None),  # noqa: B008
    since: str | None = Query(None),
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    cursor: str | None = Query(None),
) -> dict[str, Any]:
    """Return one paginated, filtered, newest-first page of events."""
    page = list_events(
        project.project_dir,
        session_id=session_id,
        kinds=kind,
        since=since,
        limit=limit,
        cursor=cursor,
    )
    return {"events": page.events, "next_cursor": page.next_cursor}


@router.get("/events/{event_id:path}")
async def get_event_route(
    event_id: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> dict[str, Any]:
    """Return the full body of one event, or 404."""
    try:
        return get_event(project.project_dir, event_id)
    except EventNotFoundError as exc:
        raise envelope_exception(
            404,
            code="event/not_found",
            detail=str(exc),
        ) from exc
