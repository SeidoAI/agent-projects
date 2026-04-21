"""WebSocket hub — per-project connection manager + broadcast fanout.

The hub tracks live :class:`fastapi.WebSocket` connections grouped by
``project_id``. Broadcast is best-effort: any send failure silently
removes the offending connection from the subscription set, so callers
never see partial-fanout errors.

Companion coroutines:

* :func:`broadcast_events` — drains the file-watcher queue into
  :meth:`WebSocketHub.broadcast`.
* :func:`heartbeat_loop` — sends a :class:`PingEvent` every 30 s so
  stalled connections get pruned quickly.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import suppress

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from tripwire.ui.events import Event, PingEvent

logger = logging.getLogger("tripwire.ui.ws.hub")

DEFAULT_HEARTBEAT_INTERVAL = 30.0


class WebSocketHub:
    """Connection manager keyed by ``project_id``."""

    def __init__(self) -> None:
        self._conns: defaultdict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, project_id: str) -> None:
        """Accept *ws* and add it to *project_id*'s subscription set."""
        await ws.accept()
        async with self._lock:
            self._conns[project_id].add(ws)

    async def disconnect(self, ws: WebSocket, project_id: str) -> None:
        """Remove *ws* from *project_id*. Idempotent."""
        async with self._lock:
            self._conns[project_id].discard(ws)
            if not self._conns[project_id]:
                self._conns.pop(project_id, None)

    async def broadcast(self, project_id: str, event: Event) -> None:
        """Send *event* to every connection registered for *project_id*.

        Connections that fail to receive (disconnect, broken pipe, etc.)
        are pruned silently — the caller is not told which ones died.
        """
        async with self._lock:
            sockets = list(self._conns.get(project_id, ()))
        if not sockets:
            return

        payload = event.to_json()
        dead: list[WebSocket] = []
        for ws in sockets:
            try:
                await ws.send_json(payload)
            except WebSocketDisconnect:
                dead.append(ws)
            except Exception:
                # Any transport error renders the socket unusable — prune it.
                logger.debug(
                    "pruning ws for project=%s after send failure",
                    project_id,
                    exc_info=True,
                )
                dead.append(ws)

        if dead:
            async with self._lock:
                bucket = self._conns.get(project_id)
                if bucket is not None:
                    for ws in dead:
                        bucket.discard(ws)
                    if not bucket:
                        self._conns.pop(project_id, None)

    async def close_all(self) -> None:
        """Close every tracked connection and clear the registry."""
        async with self._lock:
            sockets = [ws for bucket in self._conns.values() for ws in bucket]
            self._conns.clear()
        for ws in sockets:
            with suppress(Exception):
                await ws.close()

    # Back-compat alias — `server.py`'s initial scaffold calls `shutdown()`.
    shutdown = close_all

    def connection_count(self, project_id: str | None = None) -> int:
        """Return live connection count — for *project_id* or overall."""
        if project_id is None:
            return sum(len(bucket) for bucket in self._conns.values())
        return len(self._conns.get(project_id, ()))

    async def snapshot_projects(self) -> list[str]:
        """Return the project ids that currently have at least one tab."""
        async with self._lock:
            return list(self._conns.keys())


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def broadcast_events(
    queue: asyncio.Queue[Event],
    hub: WebSocketHub,
) -> None:
    """Drain *queue* into *hub*, skipping events without a ``project_id``.

    Never raises — a bad event is logged and the loop continues. Only
    cancellation exits the loop.
    """
    while True:
        event = await queue.get()
        try:
            project_id = getattr(event, "project_id", None)
            if project_id is None:
                logger.debug(
                    "broadcaster: skipping %s (no project_id)",
                    type(event).__name__,
                )
                continue
            await hub.broadcast(project_id, event)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("broadcaster failed on event %r", event)


async def heartbeat_loop(
    hub: WebSocketHub,
    *,
    interval: float = DEFAULT_HEARTBEAT_INTERVAL,
) -> None:
    """Fan out a :class:`PingEvent` to every connected tab every *interval*.

    Broken connections are pruned by :meth:`WebSocketHub.broadcast` — this
    loop doesn't need to track connection health itself.
    """
    while True:
        try:
            await asyncio.sleep(interval)
            project_ids = await hub.snapshot_projects()
            for pid in project_ids:
                await hub.broadcast(pid, PingEvent())
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("heartbeat loop error")


__all__ = [
    "DEFAULT_HEARTBEAT_INTERVAL",
    "WebSocketHub",
    "broadcast_events",
    "heartbeat_loop",
]
