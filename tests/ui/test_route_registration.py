"""Tests for route registration — all routers wired, OpenAPI complete."""

from __future__ import annotations

from fastapi.testclient import TestClient

from keel.ui.server import create_app


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
        assert r.json() == {"status": "ok"}

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

    def test_openapi_has_v2_message_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/messages" in paths
        assert "/api/messages/unread" in paths

    def test_openapi_has_v2_github_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/github/prs" in paths

    def test_openapi_has_v2_container_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/containers" in paths

    def test_openapi_has_v2_pm_reviews_routes(self):
        paths = self._get_openapi_paths()
        assert "/api/projects/{project_id}/pm-reviews" in paths

    def test_v2_stubs_return_501(self):
        app = create_app(dev_mode=True)
        client = TestClient(app)

        for path in [
            "/api/messages",
            "/api/github/prs",
            "/api/containers",
        ]:
            r = client.get(path)
            assert r.status_code == 501, f"{path} returned {r.status_code}"

    def test_total_path_count(self):
        """Sanity check: at least 20 paths registered across all modules."""
        paths = self._get_openapi_paths()
        assert len(paths) >= 20
