"""Process-event stream routes (KUI-100, KUI-155, KUI-156).

Endpoints under ``/api/projects/{project_id}``:

    GET  /events                       paginated list with filters (v0.8)
    GET  /events/{event_id}            full body of one event (v0.8)
    GET  /workflow-events              v0.9 events log list with filters
    GET  /workflow-stats               aggregate analytics over v0.9 log

Two substrates coexist:

- v0.8: `<project_dir>/.tripwire/events/<kind>/<sid>/<n>.json` via
  :mod:`tripwire.ui.services.event_aggregator`. PM-mode redaction is
  a no-op here: validator and artifact-rejection events are public;
  only tripwire prompts (in `/api/workflow`) need PM-gating.

- v0.9 (KUI-123): `<project_dir>/events/<YYYY-MM-DD>.jsonl` via
  :mod:`tripwire.ui.services.workflow_events_service`. The Event Log
  UI (KUI-155) and Process-Quality screen (KUI-156) consume this.
  Same access model — no PM-gating because tripwire prompts are
  redacted at the workflow-graph layer, not the events layer.

See `docs/specs/2026-04-26-v08-handoff.md` §2.2-§2.3.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services import workflow_events_service
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


# ---------------------------------------------------------------------------
# v0.9 workflow events log (KUI-123 substrate)
# ---------------------------------------------------------------------------


@router.get("/workflow-events")
async def list_workflow_events_route(
    project: ProjectContext = Depends(get_project),  # noqa: B008
    workflow: str | None = Query(None),
    instance: str | None = Query(None),
    station: str | None = Query(None),
    event: str | None = Query(None),
    limit: int = Query(workflow_events_service.DEFAULT_LIMIT, ge=1, le=workflow_events_service.MAX_LIMIT),
) -> dict[str, Any]:
    """Return a chronologically-ordered slice of the v0.9 events log."""
    page = workflow_events_service.list_workflow_events(
        project.project_dir,
        workflow=workflow,
        instance=instance,
        station=station,
        event=event,
        limit=limit,
    )
    return {"events": page.events, "total": page.total}


@router.get("/workflow-stats")
async def workflow_stats_route(
    project: ProjectContext = Depends(get_project),  # noqa: B008
    workflow: str | None = Query(None),
    top_n: int = Query(10, ge=0, le=100),
) -> dict[str, Any]:
    """Aggregate counts over the v0.9 events log for the Process-Quality UI."""
    aggregate = workflow_events_service.stats(
        project.project_dir,
        workflow=workflow,
        top_n=top_n,
    )
    return {
        "total": aggregate.total,
        "by_kind": aggregate.by_kind,
        "by_instance": aggregate.by_instance,
        "top_rules": aggregate.top_rules,
    }
