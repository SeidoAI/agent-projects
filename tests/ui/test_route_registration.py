"""Tests for route registration — all routers wired, OpenAPI complete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tripwire.ui.server import create_app


class TestRegisterRoutes:
    def _get_openapi_paths(self) -> list[str]:
        app = create_app(dev_mode=True)
        client = TestClient(app)
        spec = client.get("/openapi.json").json()
        return sorted(spec["paths"].keys())

    def test_health_endpoint(self):
        app = create_app(dev_mode=True)
        client = TestClient(app)
        r = client.get("/api/health")
        assert r.status_code == 200
        body = r.json()
        # v0.10.0 added service identity so the cli/ui.py single-instance
        # probe can distinguish a tripwire UI from any other service on
        # the requested port.
        assert body["status"] == "ok"
        assert body["service"] == "tripwire"
        assert "version" in body

    def test_openapi_has_project_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects" in paths
        assert "/api/projects/{project_id}" in paths

    def test_openapi_has_issue_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/issues" in paths

    def test_openapi_has_node_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/nodes" in paths

    def test_openapi_has_graph_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/graph/deps" in paths
        assert "/api/projects/{project_id}/graph/concept" in paths

    def test_openapi_has_session_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/sessions" in paths

    def test_openapi_has_artifact_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/artifact-manifest" in paths

    def test_openapi_has_enum_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/enums/{name}" in paths

    def test_openapi_has_orchestration_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/orchestration/pattern" in paths

    def test_openapi_has_action_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/actions/validate" in paths

    def test_total_path_count(self):
        """Sanity check: at least 20 paths registered across all modules."""
        paths = self._get_openapi_paths()
        assert len(paths) >= 20
