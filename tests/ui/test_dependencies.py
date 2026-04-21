"""Tests for tripwire.ui.dependencies — ProjectContext + FastAPI dependencies."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tripwire.ui.dependencies import (
    ProjectContext,
    get_event_queue,
    get_hub,
    get_project,
    reset_project_cache,
)


class TestProjectContext:
    def test_fields(self):
        fields = list(ProjectContext.__dataclass_fields__.keys())
        assert fields == ["project_id", "project_dir", "config"]

    def test_frozen(self):
        assert ProjectContext.__dataclass_params__.frozen is True


class TestGetProject:
    """Test the get_project dependency via a real FastAPI TestClient."""

    def _make_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/test/{project_id}")
        async def _route(
            project: ProjectContext = Depends(get_project),  # noqa: B008
        ) -> dict:
            return {
                "id": project.project_id,
                "name": project.config.name,
            }

        return app

    def test_happy_path(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            "name: test-proj\nkey_prefix: TST\n"
            "next_issue_number: 1\nnext_session_number: 1\n"
        )

        reset_project_cache()
        app = self._make_app()
        client = TestClient(app)

        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=proj,
        ):
            r = client.get("/test/abc123abc123")

        assert r.status_code == 200
        assert r.json()["name"] == "test-proj"
        reset_project_cache()

    def test_unknown_project_returns_404(self):
        reset_project_cache()
        app = self._make_app()
        client = TestClient(app)

        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=None,
        ):
            r = client.get("/test/deadbeef1234")

        assert r.status_code == 404
        assert "not found" in r.json()["detail"].lower()
        reset_project_cache()

    def test_missing_project_yaml_returns_500(self, tmp_path: Path):
        proj = tmp_path / "proj"
        proj.mkdir()
        # No project.yaml written

        reset_project_cache()
        app = self._make_app()
        client = TestClient(app)

        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=proj,
        ):
            r = client.get("/test/abc123abc123")

        assert r.status_code == 500
        assert "project.yaml" in r.json()["detail"].lower()
        reset_project_cache()

    def test_invalid_project_id_rejected(self):
        app = self._make_app()
        client = TestClient(app)
        r = client.get("/test/INVALID!")
        assert r.status_code == 422
        reset_project_cache()


class TestResetProjectCache:
    def test_clears_cache(self):
        from tripwire.ui.dependencies import _resolve_project_dir

        # Prime the cache
        with patch(
            "tripwire.ui.dependencies.get_project_dir",
            return_value=Path("/fake"),
        ):
            result1 = _resolve_project_dir("test_id")

        # Change the underlying return, but cache should still hold
        with patch(
            "tripwire.ui.dependencies.get_project_dir",
            return_value=Path("/other"),
        ):
            result2 = _resolve_project_dir("test_id")
        assert result2 == result1  # Still cached

        # Clear and re-resolve
        reset_project_cache()
        with patch(
            "tripwire.ui.dependencies.get_project_dir",
            return_value=Path("/other"),
        ):
            result3 = _resolve_project_dir("test_id")
        assert result3 == Path("/other")

        reset_project_cache()


class TestGetHub:
    def test_returns_hub_from_state(self):
        app = FastAPI()
        app.state.hub = "mock-hub"

        @app.get("/test-hub")
        async def _route(hub=Depends(get_hub)) -> dict:  # noqa: B008
            return {"hub": hub}

        client = TestClient(app)
        r = client.get("/test-hub")
        assert r.status_code == 200
        assert r.json()["hub"] == "mock-hub"


class TestGetEventQueue:
    def test_returns_queue_from_state(self):
        app = FastAPI()
        app.state.event_queue = asyncio.Queue()

        @app.get("/test-queue")
        async def _route(queue=Depends(get_event_queue)) -> dict:  # noqa: B008
            return {"type": type(queue).__name__}

        client = TestClient(app)
        r = client.get("/test-queue")
        assert r.status_code == 200
        assert r.json()["type"] == "Queue"
