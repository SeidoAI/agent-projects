"""Tests for `/api/projects/{project_id}/orchestration/pattern` (KUI-33)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


def _write_pattern(project_dir: Path, name: str, data: dict) -> None:
    d = project_dir / "templates" / "orchestration"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")


@pytest.fixture
def orch_project_with_pattern(tmp_path: Path) -> Path:
    proj = make_project(tmp_path / "proj")
    _write_pattern(
        proj,
        "default",
        {
            "name": "default",
            "plan_approval_required": True,
            "auto_merge_on_pass": False,
            "hooks": [
                {
                    "name": "precommit",
                    "path": "hooks/precommit.py",
                    "kind": "precommit",
                },
            ],
            "rules": [
                {
                    "event": "session_completed",
                    "condition": "status==done",
                    "action": "notify",
                    "description": "ping slack",
                },
            ],
        },
    )
    return proj


@pytest.fixture
def orch_project_without_pattern(tmp_path: Path) -> Path:
    proj = make_project(tmp_path / "proj-b")
    # No orchestration/ directory.
    return proj


@pytest.fixture
def orch_project_malformed(tmp_path: Path) -> Path:
    proj = make_project(tmp_path / "proj-c")
    d = proj / "templates" / "orchestration"
    d.mkdir(parents=True)
    (d / "default.yaml").write_text("not: [a, valid, mapping", encoding="utf-8")
    return proj


def _client_for(project: Path) -> TestClient:
    _project_svc.seed_project_index([project])
    summary = _project_svc._try_load_summary(project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    return TestClient(create_app(dev_mode=True))


def _pid(project: Path) -> str:
    return _project_svc._project_id(project.resolve())


class TestHappyPath:
    def test_returns_pattern(self, orch_project_with_pattern):
        client = _client_for(orch_project_with_pattern)
        pid = _pid(orch_project_with_pattern)
        r = client.get(f"/api/projects/{pid}/orchestration/pattern")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "default"
        assert body["plan_approval_required"] is True
        assert body["auto_merge_on_pass"] is False
        assert len(body["hooks"]) == 1
        assert len(body["rules"]) == 1

    def test_hooks_and_rules_preserve_order(self, tmp_path: Path):
        proj = make_project(tmp_path / "ordered")
        _write_pattern(
            proj,
            "default",
            {
                "rules": [
                    {"description": "first"},
                    {"description": "second"},
                    {"description": "third"},
                ]
            },
        )
        client = _client_for(proj)
        pid = _pid(proj)
        r = client.get(f"/api/projects/{pid}/orchestration/pattern")
        assert r.status_code == 200
        descs = [rule["description"] for rule in r.json()["rules"]]
        assert descs == ["first", "second", "third"]


class TestMissing:
    def test_missing_pattern_returns_404_envelope(
        self,
        orch_project_without_pattern,
    ):
        client = _client_for(orch_project_without_pattern)
        pid = _pid(orch_project_without_pattern)
        r = client.get(f"/api/projects/{pid}/orchestration/pattern")
        assert r.status_code == 404
        body = r.json()
        assert body["code"] == "orchestration/pattern_missing"


class TestMalformed:
    def test_malformed_pattern_returns_500_envelope(
        self,
        orch_project_malformed,
    ):
        client = _client_for(orch_project_malformed)
        pid = _pid(orch_project_malformed)
        r = client.get(f"/api/projects/{pid}/orchestration/pattern")
        assert r.status_code == 500
        body = r.json()
        assert body["code"] == "orchestration/pattern_invalid"


class TestOpenAPI:
    def test_registers_path(self, orch_project_with_pattern):
        client = _client_for(orch_project_with_pattern)
        schema = client.get("/openapi.json").json()
        assert "/api/projects/{project_id}/orchestration/pattern" in schema["paths"]
