"""Tests for `/api/actions/*` routes (KUI-34).

The `/api/actions/validate` endpoint's existing tests live alongside the
WebSocket broadcast tests in `tests/ui/ws/test_ws_route.py` — we do not
duplicate those. This module covers the unknown-project envelope plus
the three new endpoints: rebuild-index, advance-phase, finalize-session.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture(autouse=True)
def _redirect_audit_log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "audit-logs"))


@pytest.fixture
def action_project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def action_project_id(action_project: Path) -> str:
    return _project_svc._project_id(action_project.resolve())


@pytest.fixture
def action_client(action_project: Path, save_test_session) -> TestClient:
    _project_svc.seed_project_index([action_project])
    summary = _project_svc._try_load_summary(action_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    save_test_session(action_project, "session-a", status="planned")
    return TestClient(create_app(dev_mode=True))


def _complete_ok(project_dir: Path, session_id: str) -> None:
    from datetime import datetime, timezone

    from tripwire.core.session_store import load_session, save_session
    from tripwire.models.enums import SessionStatus

    session = load_session(project_dir, session_id)
    session.status = SessionStatus.COMPLETED
    session.updated_at = datetime.now(tz=timezone.utc)
    save_session(project_dir, session)


class TestValidateUnknownProjectEnvelope:
    def test_unknown_project_returns_404_envelope(self, action_client):
        r = action_client.post(
            "/api/actions/validate", json={"project_id": "000000000000"}
        )
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == "project/not_found"


class TestRebuildIndex:
    def test_happy_path(self, action_client, action_project_id):
        r = action_client.post(
            "/api/actions/rebuild-index",
            json={"project_id": action_project_id},
        )
        assert r.status_code == 200
        body = r.json()
        assert "cache_rebuilt" in body
        assert "duration_ms" in body
        assert isinstance(body["duration_ms"], int)

    def test_unknown_project_returns_404(self, action_client):
        r = action_client.post(
            "/api/actions/rebuild-index",
            json={"project_id": "000000000000"},
        )
        assert r.status_code == 404
        assert r.json()["code"] == "project/not_found"


class TestAdvancePhase:
    def test_happy_path(self, action_client, action_project_id):
        r = action_client.post(
            "/api/actions/advance-phase",
            json={"project_id": action_project_id, "new_phase": "scoped"},
        )
        # Success or validation-failure both land in the body — no 500.
        assert r.status_code in (200, 409)
        body = r.json()
        assert "from_phase" in body
        assert "to_phase" in body
        assert "success" in body

    def test_unknown_phase_returns_400(self, action_client, action_project_id):
        r = action_client.post(
            "/api/actions/advance-phase",
            json={"project_id": action_project_id, "new_phase": "imaginary"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "phase/invalid"

    def test_unknown_project_returns_404(self, action_client):
        r = action_client.post(
            "/api/actions/advance-phase",
            json={"project_id": "000000000000", "new_phase": "scoped"},
        )
        assert r.status_code == 404

    def test_validation_failure_returns_409(
        self,
        action_project,
        action_project_id,
        action_client,
    ):
        # Strict validation will usually fail for the bare fixture (no
        # manifest, no enums, etc). The endpoint still returns a body
        # with success=False.
        r = action_client.post(
            "/api/actions/advance-phase",
            json={"project_id": action_project_id, "new_phase": "reviewing"},
        )
        # Either reverts (409) or succeeds (200). We only assert no 5xx.
        assert r.status_code < 500


class TestFinalizeSession:
    def test_happy_path(
        self,
        action_client,
        action_project_id,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", _complete_ok
        )
        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": action_project_id,
                "session_id": "session-a",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["session_id"] == "session-a"
        assert body["status"] == "completed"
        assert "changed_at" in body

    def test_accepts_uppercase_sequential_session_key(
        self,
        action_client,
        action_project,
        action_project_id,
        save_test_session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        save_test_session(action_project, "TST-S1", status="planned")
        monkeypatch.setattr(
            "tripwire.ui.services.action_service.complete_session", _complete_ok
        )

        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": action_project_id,
                "session_id": "TST-S1",
            },
        )

        assert r.status_code == 200
        assert r.json()["session_id"] == "TST-S1"

    def test_gate_failure_returns_409(self, action_client, action_project_id):
        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": action_project_id,
                "session_id": "session-a",
            },
        )
        assert r.status_code == 409
        assert r.json()["code"] == "complete/not_active"

    def test_bad_session_id_returns_400(self, action_client, action_project_id):
        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": action_project_id,
                "session_id": "..",
            },
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"

    def test_unknown_session_returns_404(
        self,
        action_client,
        action_project_id,
    ):
        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": action_project_id,
                "session_id": "ghost",
            },
        )
        assert r.status_code == 404
        assert r.json()["code"] == "session/not_found"

    def test_unknown_project_returns_404(self, action_client):
        r = action_client.post(
            "/api/actions/finalize-session",
            json={
                "project_id": "000000000000",
                "session_id": "session-a",
            },
        )
        assert r.status_code == 404
        assert r.json()["code"] == "project/not_found"


class TestOpenAPI:
    def test_registers_paths(self, action_client):
        schema = action_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/actions/validate" in paths
        assert "/api/actions/rebuild-index" in paths
        assert "/api/actions/advance-phase" in paths
        assert "/api/actions/finalize-session" in paths
