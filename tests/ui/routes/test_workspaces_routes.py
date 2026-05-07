"""Tests for the /api/workspaces route."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from tripwire.core.workspace_store import save_workspace
from tripwire.models.workspace import Workspace
from tripwire.ui.config import UserConfig
from tripwire.ui.server import create_app
from tripwire.ui.services import workspace_service as _ws_svc


@pytest.fixture(autouse=True)
def _reset_workspace_index():
    _ws_svc.reload_workspace_index()
    yield
    _ws_svc.reload_workspace_index()


def _make_workspace(workspace_dir: Path, *, slug: str, name: str) -> Path:
    workspace_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc)
    save_workspace(
        workspace_dir,
        Workspace(
            uuid=uuid4(),
            name=name,
            slug=slug,
            description="",
            schema_version=1,
            tripwire_version="0.6.0",
            created_at=now,
            updated_at=now,
        ),
    )
    return workspace_dir


class TestListWorkspacesRoute:
    def test_empty_returns_empty_list(self, monkeypatch):
        monkeypatch.setattr(_ws_svc, "load_user_config", UserConfig)
        client = TestClient(create_app(dev_mode=True))
        r = client.get("/api/workspaces")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_discovered_workspaces(self, tmp_path: Path, monkeypatch):
        _make_workspace(tmp_path / "ws-a", slug="alpha", name="Alpha")
        _make_workspace(tmp_path / "ws-b", slug="beta", name="Beta")
        config = UserConfig(workspace_roots=[tmp_path])
        monkeypatch.setattr(_ws_svc, "load_user_config", lambda: config)
        client = TestClient(create_app(dev_mode=True))
        r = client.get("/api/workspaces")
        assert r.status_code == 200
        data = r.json()
        assert {w["slug"] for w in data} == {"alpha", "beta"}
        # Each summary carries the fields the UI needs to render groups.
        for w in data:
            assert {"id", "name", "slug", "dir", "project_slugs"}.issubset(w.keys())

    def test_summary_dirs_are_resolved_paths(self, tmp_path: Path, monkeypatch):
        ws = _make_workspace(tmp_path / "ws", slug="x", name="X")
        config = UserConfig(workspace_roots=[tmp_path])
        monkeypatch.setattr(_ws_svc, "load_user_config", lambda: config)
        client = TestClient(create_app(dev_mode=True))
        r = client.get("/api/workspaces")
        assert r.status_code == 200
        assert r.json()[0]["dir"] == str(ws.resolve())
