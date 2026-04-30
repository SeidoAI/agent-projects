"""Tests for `/api/projects/{project_id}/nodes` + reverse-refs routes (KUI-28)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def node_project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def node_project_id(node_project: Path) -> str:
    return _project_svc._project_id(node_project.resolve())


@pytest.fixture
def node_client(
    node_project: Path,
    save_test_node,
    save_test_issue,
) -> TestClient:
    _project_svc.seed_project_index([node_project])
    summary = _project_svc._try_load_summary(node_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])

    # Two nodes plus an issue that references one of them.
    save_test_node(node_project, "user-model", type="model", status="active")
    save_test_node(
        node_project,
        "api-contract",
        type="contract",
        status="draft",
    )
    save_test_issue(
        node_project,
        "KUI-1",
        body=(
            "## Context\nReferences [[user-model]].\n\n"
            "## Implements\nREQ-1\n\n## Repo scope\n- X\n\n"
            "## Requirements\n- a\n\n## Execution constraints\n"
            "If ambiguous, stop and ask.\n\n"
            "## Acceptance criteria\n- [ ] a\n\n"
            "## Test plan\n```\nuv run pytest\n```\n\n"
            "## Dependencies\nnone\n\n## Definition of Done\n- [ ] x\n"
        ),
    )
    return TestClient(create_app(dev_mode=True))


class TestListNodes:
    def test_returns_all(self, node_client, node_project_id):
        r = node_client.get(f"/api/projects/{node_project_id}/nodes")
        assert r.status_code == 200
        ids = sorted(n["id"] for n in r.json())
        assert ids == ["api-contract", "user-model"]

    def test_filter_by_type(self, node_client, node_project_id):
        r = node_client.get(
            f"/api/projects/{node_project_id}/nodes",
            params={"type": "model"},
        )
        assert [n["id"] for n in r.json()] == ["user-model"]

    def test_filter_by_status(self, node_client, node_project_id):
        r = node_client.get(
            f"/api/projects/{node_project_id}/nodes",
            params={"status": "draft"},
        )
        assert [n["id"] for n in r.json()] == ["api-contract"]

    def test_filter_by_stale_true(self, node_client, node_project, node_project_id):
        """v0.7.4 D.1 — route-level wiring for ?stale=true. Service-level
        tests already cover the filter semantics; this one pins the
        route so we notice if the query param gets dropped during a
        refactor."""
        from tripwire.core import graph_cache
        from tripwire.models.graph import GraphIndex

        # Seed a cache that marks `api-contract` as stale. Service's
        # `_load_cache_ensuring_fresh` returns this cache verbatim
        # because it exists — no rebuild runs.
        graph_cache.save_index(
            node_project,
            GraphIndex(version=graph_cache.CACHE_VERSION, stale_nodes=["api-contract"]),
        )

        r = node_client.get(
            f"/api/projects/{node_project_id}/nodes",
            params={"stale": "true"},
        )
        assert r.status_code == 200
        ids = [n["id"] for n in r.json()]
        assert ids == ["api-contract"]

    def test_filter_by_stale_false_excludes_stale(
        self, node_client, node_project, node_project_id
    ):
        """Companion to the stale=true case — ?stale=false excludes
        the stale node, leaving the fresh one."""
        from tripwire.core import graph_cache
        from tripwire.models.graph import GraphIndex

        graph_cache.save_index(
            node_project,
            GraphIndex(version=graph_cache.CACHE_VERSION, stale_nodes=["api-contract"]),
        )

        r = node_client.get(
            f"/api/projects/{node_project_id}/nodes",
            params={"stale": "false"},
        )
        assert r.status_code == 200
        ids = [n["id"] for n in r.json()]
        assert ids == ["user-model"]


class TestGetNode:
    def test_happy_path(self, node_client, node_project_id):
        r = node_client.get(f"/api/projects/{node_project_id}/nodes/user-model")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == "user-model"
        assert body["type"] == "model"
        assert "body" in body

    def test_unknown_slug_returns_404(self, node_client, node_project_id):
        r = node_client.get(f"/api/projects/{node_project_id}/nodes/does-not-exist")
        assert r.status_code == 404
        assert r.json()["code"] == "node/not_found"

    def test_malformed_slug_returns_400(self, node_client, node_project_id):
        # Uppercase → regex rejects.
        r = node_client.get(f"/api/projects/{node_project_id}/nodes/UpperCase")
        assert r.status_code == 400
        assert r.json()["code"] == "node/bad_slug"

    def test_slug_with_leading_digit_returns_400(
        self,
        node_client,
        node_project_id,
    ):
        r = node_client.get(f"/api/projects/{node_project_id}/nodes/1bad")
        assert r.status_code == 400


class TestCheckFreshness:
    def test_returns_report(self, node_client, node_project_id):
        r = node_client.post(f"/api/projects/{node_project_id}/nodes/check")
        assert r.status_code == 200
        body = r.json()
        assert "nodes" in body
        assert isinstance(body["nodes"], list)


class TestReverseRefs:
    def test_returns_referrers(self, node_client, node_project_id):
        r = node_client.get(f"/api/projects/{node_project_id}/refs/reverse/user-model")
        assert r.status_code == 200
        body = r.json()
        assert body["node_id"] == "user-model"
        ids = [ref["id"] for ref in body["referrers"]]
        assert "KUI-1" in ids

    def test_empty_for_unreferenced_node(
        self,
        node_client,
        node_project_id,
    ):
        r = node_client.get(
            f"/api/projects/{node_project_id}/refs/reverse/api-contract"
        )
        assert r.status_code == 200
        assert r.json()["referrers"] == []

    def test_malformed_slug_returns_400(self, node_client, node_project_id):
        r = node_client.get(f"/api/projects/{node_project_id}/refs/reverse/UpperCase")
        assert r.status_code == 400


class TestOpenAPI:
    def test_registers_paths(self, node_client):
        schema = node_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/projects/{project_id}/nodes" in paths
        assert "/api/projects/{project_id}/nodes/{node_id}" in paths
        assert "/api/projects/{project_id}/nodes/check" in paths
        assert "/api/projects/{project_id}/refs/reverse/{node_id}" in paths
        # Layout PATCH moved to /graph/concept/layout — see test_graph_routes.
        assert "/api/projects/{project_id}/nodes/{node_id}/layout" not in paths
