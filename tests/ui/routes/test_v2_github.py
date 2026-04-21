"""Integration tests for the v2 github stub router (KUI-43)."""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient

from tripwire.ui.routes import github as github_routes
from tripwire.ui.routes._v2_stub import V2_NOT_IMPLEMENTED_CODE
from tripwire.ui.server import create_app
from tripwire.ui.services import github_service


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(dev_mode=True))


def _assert_v2_envelope(resp) -> None:
    assert resp.status_code == 501, f"expected 501, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body, body
    detail = body["detail"]
    assert isinstance(detail, dict), detail
    assert detail["code"] == V2_NOT_IMPLEMENTED_CODE
    assert isinstance(detail.get("detail"), str) and detail["detail"]
    assert isinstance(detail.get("extras"), dict)


class TestGitHubRoutes501:
    def test_list_prs(self, client):
        _assert_v2_envelope(client.get("/api/github/prs", params={"repo": "owner/x"}))

    def test_pr_checks(self, client):
        _assert_v2_envelope(
            client.get("/api/github/prs/42/checks", params={"repo": "owner/x"})
        )

    def test_pr_reviews(self, client):
        _assert_v2_envelope(
            client.get("/api/github/prs/42/reviews", params={"repo": "owner/x"})
        )


class TestGitHubOpenAPI:
    def test_all_paths_tagged_github_v2(self, client):
        spec = client.get("/openapi.json").json()
        paths = spec["paths"]
        expected = [
            "/api/github/prs",
            "/api/github/prs/{pr_number}/checks",
            "/api/github/prs/{pr_number}/reviews",
        ]
        for path in expected:
            assert path in paths, f"missing OpenAPI path {path}"
            op = paths[path]["get"]
            assert "github (v2)" in op.get("tags", []), (
                f"{path} missing github (v2) tag"
            )


class TestNoSubprocessImport:
    """The stub must not pull in subprocess — that belongs to the v2 gh wrapper.

    ``subprocess`` is stdlib and often already loaded by transitive deps, so
    we inspect the stub source directly rather than checking ``sys.modules``.
    """

    @staticmethod
    def _imports_subprocess(module) -> bool:
        src = inspect.getsource(module)
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import subprocess", "from subprocess")):
                return True
        return False

    def test_routes_github_no_subprocess(self):
        assert not self._imports_subprocess(github_routes), (
            "tripwire.ui.routes.github must not import subprocess"
        )

    def test_services_github_no_subprocess(self):
        assert not self._imports_subprocess(github_service), (
            "tripwire.ui.services.github_service must not import subprocess"
        )
