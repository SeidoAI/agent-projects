"""Tests for `/api/projects/{project_id}/artifact-manifest` and
`/api/projects/{project_id}/sessions/{sid}/artifacts/*` routes (KUI-31)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


def _write_manifest(project_dir: Path, artifacts: list[dict]) -> None:
    tmpl = project_dir / "templates" / "artifacts"
    tmpl.mkdir(parents=True, exist_ok=True)
    (tmpl / "manifest.yaml").write_text(
        yaml.safe_dump({"artifacts": artifacts}, sort_keys=False),
        encoding="utf-8",
    )


@pytest.fixture
def artifact_project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def artifact_project_id(artifact_project: Path) -> str:
    return _project_svc._project_id(artifact_project.resolve())


@pytest.fixture
def artifact_client(
    artifact_project: Path,
    save_test_session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    # Redirect audit log (service writes sidecars atomically + audit).
    monkeypatch.setenv("TRIPWIRE_LOG_DIR", str(tmp_path / "audit-logs"))

    _project_svc.seed_project_index([artifact_project])
    summary = _project_svc._try_load_summary(artifact_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])

    _write_manifest(
        artifact_project,
        [
            {
                "name": "plan",
                "file": "plan.md",
                "template": "plan.md.j2",
                "produced_at": "planning",
                "produced_by": "pm",
                "owned_by": "pm",
                "required": True,
                "approval_gate": True,
            },
            {
                "name": "task-checklist",
                "file": "task-checklist.md",
                "template": "task-checklist.md.j2",
                "produced_at": "executing",
                "produced_by": "agent",
                "owned_by": "agent",
                "required": True,
                "approval_gate": False,
            },
        ],
    )
    save_test_session(artifact_project, "session-a", plan=True)
    save_test_session(artifact_project, "TST-S1", plan=True)
    # Write the plan artifact on disk (plan=True creates plan.md under artifacts/).
    (
        artifact_project / "sessions" / "session-a" / "artifacts" / "task-checklist.md"
    ).write_text("| # | | |\n|---|---|---|\n| 1 | task | done |\n")
    return TestClient(create_app(dev_mode=True))


class TestManifestRoute:
    def test_returns_manifest(self, artifact_client, artifact_project_id):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/artifact-manifest"
        )
        assert r.status_code == 200
        body = r.json()
        names = [a["name"] for a in body["artifacts"]]
        assert names == ["plan", "task-checklist"]


class TestListSessionArtifacts:
    def test_returns_status_list(self, artifact_client, artifact_project_id):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/session-a/artifacts"
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) == 2
        plan = next(a for a in body if a["spec"]["name"] == "plan")
        assert plan["present"] is True

    def test_accepts_uppercase_sequential_session_key(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/TST-S1/artifacts"
        )

        assert r.status_code == 200
        plan = next(a for a in r.json() if a["spec"]["name"] == "plan")
        assert plan["present"] is True

    def test_bad_session_id_returns_400(self, artifact_client, artifact_project_id):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/bad.value/artifacts"
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"


class TestGetArtifact:
    def test_happy_path(self, artifact_client, artifact_project_id):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/session-a/artifacts/plan"
        )
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "plan"
        assert "body" in body
        assert "mtime" in body

    def test_accepts_uppercase_sequential_session_key(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/TST-S1/artifacts/plan"
        )

        assert r.status_code == 200
        assert r.json()["name"] == "plan"

    def test_missing_file_returns_404(
        self,
        artifact_client,
        artifact_project_id,
        artifact_project,
    ):
        # Remove the file on disk; manifest still lists it.
        plan = artifact_project / "sessions" / "session-a" / "artifacts" / "plan.md"
        plan.unlink()
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/session-a/artifacts/plan"
        )
        assert r.status_code == 404
        assert r.json()["code"] == "artifact/not_found"

    def test_unknown_artifact_name_returns_404(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/session-a/artifacts/ghost"
        )
        assert r.status_code == 404

    def test_bad_session_id_returns_400(self, artifact_client, artifact_project_id):
        r = artifact_client.get(
            f"/api/projects/{artifact_project_id}/sessions/bad.value/artifacts/plan"
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"


class TestApproveArtifact:
    def test_happy_path_writes_sidecar(
        self,
        artifact_client,
        artifact_project_id,
        artifact_project,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/plan/approve",
            json={"feedback": "looks good"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["approval"] is not None
        assert body["approval"]["approved"] is True
        # Sidecar file on disk.
        sidecar = artifact_project / "sessions" / "session-a" / "plan.approval.yaml"
        assert sidecar.exists()

    def test_accepts_uppercase_sequential_session_key(
        self,
        artifact_client,
        artifact_project_id,
        artifact_project,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/TST-S1/artifacts/plan/approve",
            json={"feedback": "looks good"},
        )

        assert r.status_code == 200
        sidecar = artifact_project / "sessions" / "TST-S1" / "plan.approval.yaml"
        assert sidecar.exists()

    def test_no_feedback_body_ok(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/plan/approve",
            json={},
        )
        assert r.status_code == 200

    def test_ungated_artifact_returns_409(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/task-checklist/approve",
            json={},
        )
        assert r.status_code == 409
        assert r.json()["code"] == "artifact/no_gate"

    def test_bad_session_id_returns_400(self, artifact_client, artifact_project_id):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}/sessions/bad.value/artifacts/plan/approve",
            json={},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"


class TestRejectArtifact:
    def test_happy_path_requires_feedback(
        self,
        artifact_client,
        artifact_project_id,
        artifact_project,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/plan/reject",
            json={"feedback": "needs rework"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["approval"] is not None
        assert body["approval"]["approved"] is False

    def test_empty_feedback_returns_409(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/plan/reject",
            json={"feedback": "   "},
        )
        assert r.status_code == 409

    def test_missing_feedback_returns_422(
        self,
        artifact_client,
        artifact_project_id,
    ):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}"
            "/sessions/session-a/artifacts/plan/reject",
            json={},
        )
        # Pydantic required-field rejection.
        assert r.status_code == 422

    def test_bad_session_id_returns_400(self, artifact_client, artifact_project_id):
        r = artifact_client.post(
            f"/api/projects/{artifact_project_id}/sessions/bad.value/artifacts/plan/reject",
            json={"feedback": "nope"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "session/bad_slug"


class TestOpenAPI:
    def test_registers_paths(self, artifact_client):
        schema = artifact_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/projects/{project_id}/artifact-manifest" in paths
        assert "/api/projects/{project_id}/sessions/{sid}/artifacts" in paths
        assert "/api/projects/{project_id}/sessions/{sid}/artifacts/{name}" in paths
        assert (
            "/api/projects/{project_id}"
            "/sessions/{sid}/artifacts/{name}/approve" in paths
        )
        assert (
            "/api/projects/{project_id}/sessions/{sid}/artifacts/{name}/reject" in paths
        )
