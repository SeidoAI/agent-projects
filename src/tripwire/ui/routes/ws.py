"""WebSocket route — real-time event streaming at ``/api/ws?project=<id>``.

Lifespan (see :mod:`tripwire.ui.server`) starts a :class:`WebSocketHub`,
the file-watcher :class:`~watchdog.observers.Observer`, the
:func:`~tripwire.ui.ws.hub.broadcast_events` drainer, and the
:func:`~tripwire.ui.ws.hub.heartbeat_loop`. This route just holds the
socket open and shuttles inbound ``pong`` messages to ``/dev/null``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from tripwire.ui.services.project_service import get_project_dir
from tripwire.ui.ws.hub import WebSocketHub

logger = logging.getLogger("tripwire.ui.routes.ws")

router = APIRouter(tags=["ws"])

# RFC 6455 close code in the 4000-4999 application range.
# 4404 = "project not found" — mirrored on the frontend client.
PROJECT_NOT_FOUND = 4404
HUB_NOT_READY = 1011


@router.websocket("/api/ws")
async def ws_endpoint(
    ws: WebSocket,
    project: str = Query(..., pattern=r"^[a-f0-9]{12}$"),
) -> None:
    """Hold a per-tab WebSocket open for real-time events on *project*."""
    if get_project_dir(project) is None:
        # Accept first so the close code can be read by Starlette's test
        # client — ``close`` on an un-accepted socket reports as 1006.
        await ws.accept()
        await ws.close(code=PROJECT_NOT_FOUND)
        return

    hub: WebSocketHub | None = ws.app.state.hub
    if hub is None:
        await ws.accept()
        await ws.close(code=HUB_NOT_READY)
        return

    await hub.connect(ws, project)
    try:
        while True:
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "pong":
                continue
            # v1 does not accept any other inbound types — ignore silently.
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(ws, project)
