"""Tests for tripwire.ui.ws.hub — hub, broadcaster, heartbeat."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from tripwire.ui.events import (
    FileChangedEvent,
    PingEvent,
    ValidationCompletedEvent,
)
from tripwire.ui.ws.hub import (
    WebSocketHub,
    broadcast_events,
    heartbeat_loop,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    # Pin to asyncio — we rely on asyncio primitives (Queue, CancelledError).
    return "asyncio"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class FakeWebSocket:
    """Stand-in for ``fastapi.WebSocket`` — records calls, optional failure."""

    def __init__(
        self,
        *,
        fail_on_send: bool = False,
        fail_with: type[BaseException] | None = None,
    ) -> None:
        self.accepted = False
        self.closed = False
        self.sent: list[dict[str, Any]] = []
        self._fail_on_send = fail_on_send
        self._fail_with = fail_with or RuntimeError

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, Any]) -> None:
        if self._fail_on_send:
            raise self._fail_with("transport failed")
        self.sent.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = True


def _file_changed(project_id: str = "p") -> FileChangedEvent:
    return FileChangedEvent(
        project_id=project_id,
        entity_type="issue",
        entity_id="KUI-1",
        action="modified",
        path="issues/KUI-1/issue.yaml",
    )


# ---------------------------------------------------------------------------
# WebSocketHub — connect / disconnect / broadcast
# ---------------------------------------------------------------------------


class TestHubLifecycle:
    async def test_connect_accepts_and_registers(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        assert ws.accepted is True
        assert hub.connection_count("p") == 1
        assert hub.connection_count() == 1

    async def test_disconnect_removes(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        await hub.disconnect(ws, "p")
        assert hub.connection_count("p") == 0

    async def test_disconnect_idempotent(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        await hub.disconnect(ws, "p")
        await hub.disconnect(ws, "p")  # no-op — does not raise
        assert hub.connection_count("p") == 0

    async def test_connection_count_per_project(self):
        hub = WebSocketHub()
        await hub.connect(FakeWebSocket(), "a")
        await hub.connect(FakeWebSocket(), "a")
        await hub.connect(FakeWebSocket(), "b")
        assert hub.connection_count("a") == 2
        assert hub.connection_count("b") == 1
        assert hub.connection_count() == 3
        assert hub.connection_count("missing") == 0

    async def test_snapshot_projects(self):
        hub = WebSocketHub()
        await hub.connect(FakeWebSocket(), "a")
        await hub.connect(FakeWebSocket(), "b")
        projects = await hub.snapshot_projects()
        assert sorted(projects) == ["a", "b"]


class TestBroadcast:
    async def test_all_subscribers_receive(self):
        hub = WebSocketHub()
        a, b = FakeWebSocket(), FakeWebSocket()
        await hub.connect(a, "p")
        await hub.connect(b, "p")
        await hub.broadcast("p", _file_changed())
        assert len(a.sent) == 1
        assert len(b.sent) == 1
        assert a.sent[0]["type"] == "file_changed"

    async def test_other_project_isolated(self):
        hub = WebSocketHub()
        a, b = FakeWebSocket(), FakeWebSocket()
        await hub.connect(a, "p")
        await hub.connect(b, "q")
        await hub.broadcast("p", _file_changed(project_id="p"))
        assert len(a.sent) == 1
        assert len(b.sent) == 0

    async def test_dead_connection_pruned_mid_broadcast(self):
        hub = WebSocketHub()
        good, dead = FakeWebSocket(), FakeWebSocket(fail_on_send=True)
        await hub.connect(good, "p")
        await hub.connect(dead, "p")
        # Broadcast does NOT raise — dead socket is pruned silently.
        await hub.broadcast("p", _file_changed())
        assert hub.connection_count("p") == 1
        # A second broadcast only reaches the survivor.
        await hub.broadcast("p", _file_changed())
        assert len(good.sent) == 2

    async def test_websocket_disconnect_pruned(self):
        hub = WebSocketHub()
        dead = FakeWebSocket(fail_on_send=True, fail_with=WebSocketDisconnect)
        await hub.connect(dead, "p")
        await hub.broadcast("p", _file_changed())
        assert hub.connection_count("p") == 0

    async def test_broadcast_no_connections_is_noop(self):
        hub = WebSocketHub()
        await hub.broadcast("p", _file_changed())  # must not raise

    async def test_concurrent_connect_disconnect(self):
        hub = WebSocketHub()
        sockets = [FakeWebSocket() for _ in range(20)]

        await asyncio.gather(*(hub.connect(ws, "p") for ws in sockets))
        assert hub.connection_count("p") == 20

        await asyncio.gather(*(hub.disconnect(ws, "p") for ws in sockets[:10]))
        assert hub.connection_count("p") == 10

        # Broadcast still works and only reaches the survivors.
        await hub.broadcast("p", _file_changed())
        for ws in sockets[10:]:
            assert len(ws.sent) == 1
        for ws in sockets[:10]:
            assert len(ws.sent) == 0


class TestCloseAll:
    async def test_closes_every_socket(self):
        hub = WebSocketHub()
        wss = [FakeWebSocket() for _ in range(3)]
        for ws in wss:
            await hub.connect(ws, "p")
        await hub.close_all()
        for ws in wss:
            assert ws.closed is True
        assert hub.connection_count() == 0

    async def test_shutdown_alias(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        await hub.shutdown()  # alias to close_all
        assert ws.closed is True


# ---------------------------------------------------------------------------
# broadcast_events()
# ---------------------------------------------------------------------------


class TestBroadcastEvents:
    async def test_drains_queue_into_hub(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(broadcast_events(queue, hub))
        try:
            for _ in range(5):
                await queue.put(_file_changed())
            # Let the task drain.
            for _ in range(50):
                if len(ws.sent) == 5:
                    break
                await asyncio.sleep(0.01)
            assert len(ws.sent) == 5
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_survives_bad_event(self):
        """A dispatch exception on one event must not kill the loop."""

        class ExplodingHub(WebSocketHub):
            def __init__(self) -> None:
                super().__init__()
                self.calls = 0

            async def broadcast(self, project_id, event):  # type: ignore[override]
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("kaboom")

        hub = ExplodingHub()
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(broadcast_events(queue, hub))
        try:
            await queue.put(_file_changed())  # raises inside broadcast
            await queue.put(_file_changed())  # must still be processed
            for _ in range(50):
                if hub.calls >= 2:
                    break
                await asyncio.sleep(0.01)
            assert hub.calls >= 2
            assert not task.done()
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_skips_event_without_project_id(self):
        """A PingEvent (no project_id) on the queue is logged and skipped."""
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(broadcast_events(queue, hub))
        try:
            await queue.put(PingEvent())
            await queue.put(_file_changed())
            for _ in range(50):
                if ws.sent:
                    break
                await asyncio.sleep(0.01)
            # Only the file_changed event fanned out.
            assert len(ws.sent) == 1
            assert ws.sent[0]["type"] == "file_changed"
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_dispatches_validation_completed(self):
        hub = WebSocketHub()
        ws = FakeWebSocket()
        await hub.connect(ws, "p")
        queue: asyncio.Queue = asyncio.Queue()
        task = asyncio.create_task(broadcast_events(queue, hub))
        try:
            await queue.put(
                ValidationCompletedEvent(
                    project_id="p", errors=0, warnings=0, duration_ms=1
                )
            )
            for _ in range(50):
                if ws.sent:
                    break
                await asyncio.sleep(0.01)
            assert ws.sent[0]["type"] == "validation_completed"
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


# ---------------------------------------------------------------------------
# heartbeat_loop()
# ---------------------------------------------------------------------------


class TestHeartbeatLoop:
    async def test_pings_every_connected_project(self):
        hub = WebSocketHub()
        a = FakeWebSocket()
        b = FakeWebSocket()
        await hub.connect(a, "proj1")
        await hub.connect(b, "proj2")

        task = asyncio.create_task(heartbeat_loop(hub, interval=0.02))
        try:
            for _ in range(100):
                if a.sent and b.sent:
                    break
                await asyncio.sleep(0.01)
            assert a.sent and a.sent[0]["type"] == "ping"
            assert b.sent and b.sent[0]["type"] == "ping"
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_prunes_dead_connections(self):
        hub = WebSocketHub()
        dead = FakeWebSocket(fail_on_send=True)
        await hub.connect(dead, "p")
        task = asyncio.create_task(heartbeat_loop(hub, interval=0.02))
        try:
            for _ in range(100):
                if hub.connection_count("p") == 0:
                    break
                await asyncio.sleep(0.01)
            assert hub.connection_count("p") == 0
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    async def test_cancellation_exits_cleanly(self):
        hub = WebSocketHub()
        task = asyncio.create_task(heartbeat_loop(hub, interval=0.02))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
