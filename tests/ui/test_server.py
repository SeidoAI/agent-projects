"""Tests for tripwire.ui.server — app factory, lifespan, start_server."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tripwire.ui.server import create_app, start_server


class TestCreateApp:
    def test_returns_fastapi_instance(self):
        app = create_app(dev_mode=True)
        assert isinstance(app, FastAPI)

    def test_title_and_version(self):
        import tripwire

        app = create_app(dev_mode=True)
        assert app.title == "Tripwire UI"
        assert app.version == tripwire.__version__

    def test_openapi_json_available(self):
        app = create_app(dev_mode=True)
        client = TestClient(app)
        r = client.get("/openapi.json")
        assert r.status_code == 200
        assert "paths" in r.json()

    def test_docs_available(self):
        app = create_app(dev_mode=True)
        client = TestClient(app)
        r = client.get("/docs")
        assert r.status_code == 200


class TestLifespan:
    def test_event_queue_created_on_startup(self):
        import asyncio

        app = create_app(dev_mode=True)
        with TestClient(app):
            assert isinstance(app.state.event_queue, asyncio.Queue)

    def test_hub_initialised(self):
        from tripwire.ui.ws.hub import WebSocketHub

        app = create_app(dev_mode=True)
        with TestClient(app):
            assert isinstance(app.state.hub, WebSocketHub)

    def test_observer_initialised(self):
        from watchdog.observers.api import BaseObserver

        app = create_app(dev_mode=True)
        with TestClient(app):
            assert isinstance(app.state.observer, BaseObserver)
            assert app.state.observer.is_alive()

    def test_background_tasks_scheduled(self):
        app = create_app(dev_mode=True)
        with TestClient(app):
            assert app.state.broadcaster_task is not None
            assert not app.state.broadcaster_task.done()
            assert app.state.heartbeat_task is not None
            assert not app.state.heartbeat_task.done()

    def test_lifespan_enters_and_exits_cleanly(self):
        app = create_app(dev_mode=True)
        # TestClient triggers lifespan enter/exit without raising
        with TestClient(app) as client:
            r = client.get("/api/health")
            assert r.status_code == 200


class TestStartServer:
    def test_calls_uvicorn_run(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\n"
            "next_issue_number: 1\nnext_session_number: 1\n"
        )

        with patch("uvicorn.run") as mock_uvicorn_run:
            start_server(
                host="127.0.0.1",
                port=0,
                project_dirs=[proj],
                dev_mode=True,
                open_browser=False,
            )

        mock_uvicorn_run.assert_called_once()
        call_kwargs = mock_uvicorn_run.call_args.kwargs
        assert call_kwargs["host"] == "127.0.0.1"
        assert call_kwargs["port"] == 0
        assert isinstance(mock_uvicorn_run.call_args.args[0], FastAPI)

    def test_stores_project_dirs_on_state(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\n"
            "next_issue_number: 1\nnext_session_number: 1\n"
        )

        captured_app = None

        def _capture_app(app, **kwargs):
            nonlocal captured_app
            captured_app = app

        with patch("uvicorn.run", side_effect=_capture_app):
            start_server(
                host="127.0.0.1",
                port=0,
                project_dirs=[proj],
                dev_mode=True,
                open_browser=False,
            )

        assert captured_app is not None
        assert captured_app.state.project_dirs == [proj]

    def test_seeds_project_index(self, tmp_path: Path):
        from tripwire.ui.services.project_service import (
            _project_id,
            get_project_dir,
            reload_project_index,
        )

        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test\nkey_prefix: TST\n"
            "next_issue_number: 1\nnext_session_number: 1\n"
        )

        reload_project_index()

        with patch("uvicorn.run"):
            start_server(
                host="127.0.0.1",
                port=0,
                project_dirs=[proj],
                dev_mode=True,
                open_browser=False,
            )

        pid = _project_id(proj.resolve())
        assert get_project_dir(pid) == proj.resolve()

        # Cleanup
        reload_project_index()
