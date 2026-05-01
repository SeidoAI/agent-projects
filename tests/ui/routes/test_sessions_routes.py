"""Tests for `/api/projects/{project_id}/sessions` routes (KUI-30)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def sess_project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def sess_project_id(sess_project: Path) -> str:
    return _project_svc._project_id(sess_project.resolve())


@pytest.fixture
def empty_sessions_client(sess_project: Path) -> TestClient:
    _project_svc.seed_project_index([sess_project])
    summary = _project_svc._try_load_summary(sess_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    return TestClient(create_app(dev_mode=True))


@pytest.fixture
def session_client(sess_project: Path, save_test_session) -> TestClient:
    _project_svc.seed_project_index([sess_project])
    summary = _project_svc._try_load_summary(sess_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    save_test_session(sess_project, "session-a", plan=True, status="planned")
    save_test_session(
        sess_project,
        "session-b",
        plan=True,
        status="completed",
    )
    return TestClient(create_app(dev_mode=True))


class TestListSessions:
    def test_returns_all(self, session_client, sess_project_id):
        r = session_client.get(f"/api/projects/{sess_project_id}/sessions")
        assert r.status_code == 200
        ids = sorted(s["id"] for s in r.json())
        assert ids == ["session-a", "session-b"]

    def test_filter_by_status(self, session_client, sess_project_id):
        r = session_client.get(
            f"/api/projects/{sess_project_id}/sessions",
            params={"status": "planned"},
        )
        assert [s["id"] for s in r.json()] == ["session-a"]

    def test_unknown_status_returns_empty(self, session_client, sess_project_id):
        r = session_client.get(
            f"/api/projects/{sess_project_id}/sessions",
            params={"status": "imaginary"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_empty_project_returns_empty(
        self,
        empty_sessions_client,
        sess_project_id,
    ):
        r = empty_sessions_client.get(f"/api/projects/{sess_project_id}/sessions")
        assert r.status_code == 200
        assert r.json() == []


class TestGetSession:
    def test_happy_path(self, session_client, sess_project_id):
        r = session_client.get(f"/api/projects/{sess_project_id}/sessions/session-a")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "session-a"
        assert body["status"] == "planned"
        assert "plan_md" in body
        assert "artifact_status" in body
        assert "task_progress" in body

    def test_unknown_sid_returns_404_envelope(
        self,
        session_client,
        sess_project_id,
    ):
        r = session_client.get(
            f"/api/projects/{sess_project_id}/sessions/does-not-exist"
        )
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == "session/not_found"
        assert "does-not-exist" in body["detail"]

    def test_uppercase_sequential_session_key_returns_detail(
        self,
        session_client,
        sess_project_id,
        sess_project,
        save_test_session,
    ):
        save_test_session(sess_project, "TST-S1", plan=True, status="planned")

        r = session_client.get(f"/api/projects/{sess_project_id}/sessions/TST-S1")

        assert r.status_code == 200
        assert r.json()["id"] == "TST-S1"

    def test_malformed_sid_returns_400(
        self,
        session_client,
        sess_project_id,
    ):
        r = session_client.get(f"/api/projects/{sess_project_id}/sessions/bad.value")
        assert r.status_code == 400


class TestPauseSession:
    """`POST /api/projects/{pid}/sessions/{sid}/pause` — KUI-107 INTERVENE.

    Mirrors the CLI ``tripwire session pause`` semantics: only an
    ``executing`` session can be paused; a dead PID flips status to
    ``failed`` rather than ``paused`` (matches the live state); a
    runtime-pause failure leaves status as ``executing`` and surfaces
    a 409 envelope.
    """

    @pytest.fixture
    def executing_session_client(
        self, sess_project: Path, save_test_session
    ) -> TestClient:
        _project_svc.seed_project_index([sess_project])
        summary = _project_svc._try_load_summary(sess_project.resolve())
        if summary is not None:
            _project_svc._discovery_cache = (time.monotonic(), [summary])
        save_test_session(
            sess_project,
            "live-session",
            plan=True,
            status="executing",
        )
        return TestClient(create_app(dev_mode=True))

    def test_executing_session_pauses(
        self, executing_session_client, sess_project_id, sess_project
    ):
        r = executing_session_client.post(
            f"/api/projects/{sess_project_id}/sessions/live-session/pause"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == "live-session"
        assert body["status"] == "paused"
        assert "changed_at" in body

        # Verify on disk too — the route must persist the new status.
        from tripwire.core.session_store import load_session

        sess = load_session(sess_project, "live-session")
        assert sess.status == "paused"

    def test_uppercase_sequential_session_key_pauses(
        self,
        executing_session_client,
        sess_project_id,
        sess_project,
        save_test_session,
    ):
        save_test_session(sess_project, "TST-S1", plan=True, status="executing")

        r = executing_session_client.post(
            f"/api/projects/{sess_project_id}/sessions/TST-S1/pause"
        )

        assert r.status_code == 200, r.text
        assert r.json()["session_id"] == "TST-S1"

    def test_non_executing_session_returns_409(self, session_client, sess_project_id):
        # session-a is `planned` per the session_client fixture.
        r = session_client.post(
            f"/api/projects/{sess_project_id}/sessions/session-a/pause"
        )
        assert r.status_code == 409
        body = r.json()
        assert body["code"] == "session/bad_status"
        assert "executing" in body["detail"]

    def test_unknown_session_returns_404(
        self, executing_session_client, sess_project_id
    ):
        r = executing_session_client.post(
            f"/api/projects/{sess_project_id}/sessions/missing-session/pause"
        )
        assert r.status_code == 404
        assert r.json()["code"] == "session/not_found"

    def test_bad_slug_returns_400(self, executing_session_client, sess_project_id):
        r = executing_session_client.post(
            f"/api/projects/{sess_project_id}/sessions/bad.value/pause"
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"

    def test_dead_pid_falls_through_to_failed(
        self,
        sess_project: Path,
        sess_project_id: str,
        save_test_session,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """When the session has a non-null PID that is no longer alive,
        the pause route flips status to ``failed`` rather than lying
        about a runtime that already exited. Mirrors the same fall-through
        the CLI's ``tripwire session pause`` performs.
        """
        _project_svc.seed_project_index([sess_project])
        summary = _project_svc._try_load_summary(sess_project.resolve())
        if summary is not None:
            _project_svc._discovery_cache = (time.monotonic(), [summary])
        save_test_session(
            sess_project,
            "live-session",
            plan=True,
            status="executing",
            runtime_state={"pid": 12345},
        )

        # Force is_alive(pid) to return False so the route hits the
        # dead-PID branch deterministically (PID 12345 might happen to
        # belong to a real process on the CI host).
        from tripwire.core import process_helpers as _ph
        from tripwire.ui.services import action_service as _action_svc

        monkeypatch.setattr(_ph, "is_alive", lambda pid: False)
        monkeypatch.setattr(_action_svc, "load_session", _action_svc.load_session)

        client = TestClient(create_app(dev_mode=True))
        r = client.post(f"/api/projects/{sess_project_id}/sessions/live-session/pause")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "failed"
        assert body["session_id"] == "live-session"

        # Persisted on disk.
        from tripwire.core.session_store import load_session

        sess = load_session(sess_project, "live-session")
        assert sess.status == "failed"

        # Audit-log entry was written so a verifier can reconstruct
        # the dead-PID branch later.
        from tripwire.ui.services._audit import audit_log_path

        audit_text = audit_log_path(sess_project).read_text(encoding="utf-8")
        assert "actions.pause_session" in audit_text
        assert "dead_pid" in audit_text


class TestOpenAPI:
    def test_registers_paths(self, session_client):
        schema = session_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/projects/{project_id}/sessions" in paths
        assert "/api/projects/{project_id}/sessions/{sid}" in paths
        assert "/api/projects/{project_id}/sessions/{sid}/pause" in paths
