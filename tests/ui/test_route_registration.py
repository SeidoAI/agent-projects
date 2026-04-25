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

        # ``?session_id=`` and ``?repo=`` are required query params on their
        # respective endpoints (see [[api-rest-contract]] v2 section); without
        # them FastAPI correctly returns 422 before the 501 helper fires.
        for path in [
            "/api/messages?session_id=s1",
            "/api/github/prs?repo=owner/x",
            "/api/containers",
        ]:
            r = client.get(path)
            assert r.status_code == 501, f"{path} returned {r.status_code}"

    def test_v2_stub_endpoints_advertise_501_envelope_schema(self):
        """Every v2-stub endpoint that 501s must declare the canonical
        ``V2NotImplementedEnvelope`` schema in its OpenAPI 501 response.

        Frontend clients generated from the OpenAPI document use this to
        type the error envelope; without the annotation, generated code
        falls back to ``unknown`` and the ``isV2NotImplemented(err)``
        detector loses its compile-time guarantee.

        ``/api/messages/unread`` is intentionally excluded — it returns
        200 with ``{"count": 0}`` in v1 (KUI-73).
        """
        app = create_app(dev_mode=True)
        client = TestClient(app)
        spec = client.get("/openapi.json").json()
        paths = spec["paths"]

        v2_stub_endpoints: list[tuple[str, str]] = [
            # containers (7)
            ("/api/containers", "get"),
            ("/api/containers/{container_id}/stats", "get"),
            ("/api/containers/{container_id}/logs", "get"),
            ("/api/containers/launch", "post"),
            ("/api/containers/{container_id}/stop", "post"),
            ("/api/containers/{container_id}/terminal", "post"),
            ("/api/containers/cleanup", "post"),
            # messages (4 — /unread now 200)
            ("/api/messages", "post"),
            ("/api/messages", "get"),
            ("/api/messages/pending", "get"),
            ("/api/messages/{message_id}/respond", "post"),
            # github (3)
            ("/api/github/prs", "get"),
            ("/api/github/prs/{pr_number}/checks", "get"),
            ("/api/github/prs/{pr_number}/reviews", "get"),
            # pm-reviews (3)
            ("/api/projects/{project_id}/pm-reviews", "get"),
            ("/api/projects/{project_id}/pm-reviews/{pr_number}", "get"),
            ("/api/projects/{project_id}/pm-reviews/{pr_number}/run", "post"),
        ]

        for path, method in v2_stub_endpoints:
            assert path in paths, f"missing OpenAPI path {path}"
            op = paths[path][method]
            responses = op.get("responses", {})
            assert "501" in responses, (
                f"{method.upper()} {path} has no 501 response declared"
            )
            schema = responses["501"]["content"]["application/json"]["schema"]
            ref = schema.get("$ref", "")
            assert ref.endswith("/V2NotImplementedEnvelope"), (
                f"{method.upper()} {path} 501 schema is {schema!r}, expected "
                f"$ref to V2NotImplementedEnvelope"
            )

        # Sanity: the unread endpoint must NOT advertise 501.
        unread_responses = paths["/api/messages/unread"]["get"].get("responses", {})
        assert "501" not in unread_responses, (
            "/api/messages/unread is now 200 in v1 — the 501 annotation "
            "should not be on it"
        )

    def test_total_path_count(self):
        """Sanity check: at least 20 paths registered across all modules."""
        paths = self._get_openapi_paths()
        assert len(paths) >= 20
