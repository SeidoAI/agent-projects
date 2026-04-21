"""Integration tests for the v2 pm-reviews stub router (KUI-44)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tripwire.ui.dependencies import reset_project_cache
from tripwire.ui.routes._v2_stub import V2_NOT_IMPLEMENTED_CODE
from tripwire.ui.server import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(dev_mode=True))


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "project.yaml").write_text(
        "name: test-proj\nkey_prefix: TST\n"
        "next_issue_number: 1\nnext_session_number: 1\n"
    )
    reset_project_cache()
    yield proj
    reset_project_cache()


def _assert_v2_envelope(resp) -> None:
    assert resp.status_code == 501, f"expected 501, got {resp.status_code}"
    body = resp.json()
    assert "detail" in body, body
    detail = body["detail"]
    assert isinstance(detail, dict), detail
    assert detail["code"] == V2_NOT_IMPLEMENTED_CODE
    assert isinstance(detail.get("detail"), str) and detail["detail"]
    assert isinstance(detail.get("extras"), dict)


class TestPmReviewRoutes501:
    """Valid project id — expect 501 on every endpoint."""

    def test_list_reviews(self, client, project_dir):
        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=project_dir,
        ):
            _assert_v2_envelope(
                client.get("/api/projects/abc123abc123/pm-reviews")
            )

    def test_get_review(self, client, project_dir):
        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=project_dir,
        ):
            _assert_v2_envelope(
                client.get("/api/projects/abc123abc123/pm-reviews/42")
            )

    def test_run_review(self, client, project_dir):
        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=project_dir,
        ):
            _assert_v2_envelope(
                client.post("/api/projects/abc123abc123/pm-reviews/42/run")
            )


class TestPmReviewUnknownProject:
    """Unknown project id — project dependency runs first and returns 404."""

    def test_unknown_project_returns_404(self, client):
        reset_project_cache()
        with patch(
            "tripwire.ui.dependencies._resolve_project_dir",
            return_value=None,
        ):
            r = client.get("/api/projects/deadbeef1234/pm-reviews")
        assert r.status_code == 404, f"expected 404, got {r.status_code}"
        reset_project_cache()


class TestPmReviewOpenAPI:
    def test_all_paths_tagged_pm_reviews_v2(self, client):
        spec = client.get("/openapi.json").json()
        paths = spec["paths"]
        expected = {
            "/api/projects/{project_id}/pm-reviews": ("get",),
            "/api/projects/{project_id}/pm-reviews/{pr_number}": ("get",),
            "/api/projects/{project_id}/pm-reviews/{pr_number}/run": ("post",),
        }
        for path, methods in expected.items():
            assert path in paths, f"missing OpenAPI path {path}"
            for method in methods:
                op = paths[path][method]
                assert "pm-reviews (v2)" in op.get("tags", []), (
                    f"{path}.{method} missing pm-reviews (v2) tag"
                )
