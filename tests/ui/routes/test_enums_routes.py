"""Tests for `/api/projects/{project_id}/enums/{name}` route (KUI-32)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def enum_project(tmp_path: Path) -> Path:
    proj = make_project(tmp_path / "proj")
    enums = proj / "enums"
    enums.mkdir()
    # Structured form.
    (enums / "issue_status.yaml").write_text(
        yaml.safe_dump(
            {
                "values": [
                    {"value": "todo", "label": "Todo", "color": "#888"},
                    {"value": "done", "label": "Done", "color": "#0a0"},
                ]
            }
        ),
        encoding="utf-8",
    )
    # Flat-list form.
    (enums / "priority.yaml").write_text(
        yaml.safe_dump(["low", "medium", "high"]),
        encoding="utf-8",
    )
    return proj


@pytest.fixture
def enum_project_id(enum_project: Path) -> str:
    return _project_svc._project_id(enum_project.resolve())


@pytest.fixture
def enum_client(enum_project: Path) -> TestClient:
    _project_svc.seed_project_index([enum_project])
    summary = _project_svc._try_load_summary(enum_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    return TestClient(create_app(dev_mode=True))


class TestGetEnum:
    def test_structured_form(self, enum_client, enum_project_id):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/issue_status")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "issue_status"
        values = [v["value"] for v in body["values"]]
        assert values == ["todo", "done"]
        # colour preserved
        assert body["values"][0]["color"] == "#888"

    def test_flat_list_form(self, enum_client, enum_project_id):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/priority")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "priority"
        values = [v["value"] for v in body["values"]]
        assert values == ["low", "medium", "high"]

    def test_unknown_enum_returns_404(self, enum_client, enum_project_id):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/does_not_exist")
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == "enum/not_found"

    def test_malformed_uppercase_returns_422(
        self,
        enum_client,
        enum_project_id,
    ):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/ISSUE_STATUS")
        # FastAPI path regex mismatch → 422.
        assert r.status_code == 422

    def test_hyphen_rejected(self, enum_client, enum_project_id):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/issue-status")
        assert r.status_code == 422

    def test_leading_digit_rejected(self, enum_client, enum_project_id):
        r = enum_client.get(f"/api/projects/{enum_project_id}/enums/1status")
        assert r.status_code == 422


class TestOpenAPI:
    def test_registers_path(self, enum_client):
        schema = enum_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/projects/{project_id}/enums/{name}" in paths

    def test_response_refs_enum_descriptor(self, enum_client):
        schema = enum_client.get("/openapi.json").json()
        op = schema["paths"]["/api/projects/{project_id}/enums/{name}"]["get"]
        ref = op["responses"]["200"]["content"]["application/json"]["schema"]
        assert "EnumDescriptor" in ref["$ref"]
