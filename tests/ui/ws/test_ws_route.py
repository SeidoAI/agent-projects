"""End-to-end tests for the /api/ws route + lifespan wiring.

These tests use Starlette's TestClient WebSocket support — ``with
client.websocket_connect(...)`` drives a real server instance through
the lifespan. The file-watcher, broadcaster, and heartbeat tasks are all
live during the test.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tripwire.ui.server import create_app
from tripwire.ui.services.project_service import (
    _project_id,
    reload_project_index,
    seed_project_index,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_project(tmp_path: Path) -> tuple[Path, str]:
    """Create an on-disk project and seed the UI's project index."""
    project = tmp_path / "proj"
    project.mkdir()
    (project / "project.yaml").write_text(
        "name: t\nkey_prefix: T\n"
        "next_issue_number: 1\nnext_session_number: 1\n"
    )
    (project / "issues" / "T-1").mkdir(parents=True)
    (project / "nodes").mkdir()
    reload_project_index()
    seed_project_index([project])
    pid = _project_id(project.resolve())
    yield project, pid
    reload_project_index()


@pytest.fixture
def app_and_client(ui_project):
    """App + TestClient wired to *ui_project* so the observer watches it."""
    project, _pid = ui_project
    app = create_app(dev_mode=True)
    app.state.project_dirs = [project]
    with TestClient(app) as client:
        yield app, client


# ---------------------------------------------------------------------------
# Connection handshake
# ---------------------------------------------------------------------------


class TestConnectionHandshake:
    def test_unknown_project_closes_with_4404(self, app_and_client):
        _app, client = app_and_client
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(
                "/api/ws?project=000000000000"
            ) as ws:
                ws.receive_json()  # force dispatch
        assert exc_info.value.code == 4404

    def test_invalid_project_param_rejected(self, app_and_client):
        _app, client = app_and_client
        # Capital letters are outside the [a-f0-9]{12} regex.
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/ws?project=NOT-HEX!") as _ws:
                pass

    def test_known_project_accepts(self, app_and_client, ui_project):
        _project, pid = ui_project
        _app, client = app_and_client
        with client.websocket_connect(f"/api/ws?project={pid}") as _ws:
            # If we got here, the server accepted the handshake.
            pass


# ---------------------------------------------------------------------------
# Event delivery through the full pipeline
# ---------------------------------------------------------------------------


class TestEventDelivery:
    def test_file_change_reaches_connected_client(
        self, app_and_client, ui_project
    ):
        project, pid = ui_project
        _app, client = app_and_client

        with client.websocket_connect(f"/api/ws?project={pid}") as ws:
            # Let the observer settle before touching the filesystem.
            time.sleep(0.15)
            (project / "issues" / "T-1" / "issue.yaml").write_text(
                "title: t"
            )

            event = _poll_event(
                ws,
                "file_changed",
                timeout=3.0,
                match={"entity_type": "issue", "entity_id": "T-1"},
            )

        assert event is not None and event["type"] == "file_changed"
        assert event["entity_type"] == "issue"
        assert event["entity_id"] == "T-1"
        assert event["project_id"] == pid

    def test_two_clients_both_receive(self, app_and_client, ui_project):
        project, pid = ui_project
        _app, client = app_and_client

        with (
            client.websocket_connect(f"/api/ws?project={pid}") as ws_a,
            client.websocket_connect(f"/api/ws?project={pid}") as ws_b,
        ):
            time.sleep(0.15)
            (project / "nodes" / "shared.yaml").write_text("x: 1")

            match = {"entity_type": "node", "entity_id": "shared"}
            a = _poll_event(ws_a, "file_changed", timeout=3.0, match=match)
            b = _poll_event(ws_b, "file_changed", timeout=3.0, match=match)

        assert a is not None and a["entity_type"] == "node"
        assert b is not None and b["entity_type"] == "node"

    def test_pong_is_accepted(self, app_and_client, ui_project):
        project, pid = ui_project
        _app, client = app_and_client
        with client.websocket_connect(f"/api/ws?project={pid}") as ws:
            ws.send_json({"type": "pong"})
            # The server just swallows pong messages. Trigger a real event
            # to prove the connection is still live after the pong.
            time.sleep(0.15)
            (project / "issues" / "T-1" / "issue.yaml").write_text(
                "title: t"
            )
            event = _poll_event(
                ws,
                "file_changed",
                timeout=3.0,
                match={"entity_type": "issue", "entity_id": "T-1"},
            )
        assert event is not None and event["entity_type"] == "issue"


# ---------------------------------------------------------------------------
# Validation-action → broadcast
# ---------------------------------------------------------------------------


class TestValidationEvent:
    def test_validate_endpoint_broadcasts_to_clients(
        self, app_and_client, ui_project
    ):
        _project, pid = ui_project
        _app, client = app_and_client
        with client.websocket_connect(f"/api/ws?project={pid}") as ws:
            r = client.post(
                "/api/actions/validate", json={"project_id": pid}
            )
            assert r.status_code == 200
            assert r.json()["type"] == "validation_completed"

            event = _poll_event(ws, "validation_completed", timeout=2.0)

        assert event is not None
        assert event["project_id"] == pid
        assert event["errors"] == 0
        assert event["warnings"] == 0

    def test_validate_unknown_project_404(self, app_and_client):
        _app, client = app_and_client
        r = client.post(
            "/api/actions/validate", json={"project_id": "000000000000"}
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Lifespan shutdown
# ---------------------------------------------------------------------------


class TestLifespan:
    def test_enters_and_exits_cleanly(self, ui_project):
        project, _pid = ui_project
        app = create_app(dev_mode=True)
        app.state.project_dirs = [project]
        # No exception = clean startup/shutdown.
        with TestClient(app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200

        # After shutdown the background tasks should be done.
        assert app.state.broadcaster_task.done()
        assert app.state.heartbeat_task.done()
        assert not app.state.observer.is_alive()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _poll_event(
    ws,
    expected_type: str,
    *,
    timeout: float,
    match: dict[str, str] | None = None,
) -> dict | None:
    """Consume events from *ws* until one matches *expected_type* + *match*.

    The observer often emits spurious ``file_changed`` events for the
    existing ``project.yaml`` (FSEvents replays it on observer startup).
    Callers pass a ``match`` dict when they want to latch onto the exact
    write they made, not the replay.
    """
    match = match or {}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            msg = ws.receive_json(mode="text")
        except Exception:
            continue
        if msg.get("type") != expected_type:
            continue
        if all(msg.get(k) == v for k, v in match.items()):
            return msg
    return None
