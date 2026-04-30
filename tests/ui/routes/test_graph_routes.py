"""Tests for `/api/projects/{project_id}/graph/*` routes (KUI-29)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.ui.routes.conftest import make_project
from tripwire.ui.server import create_app
from tripwire.ui.services import project_service as _project_svc


@pytest.fixture
def graph_project(tmp_path: Path) -> Path:
    return make_project(tmp_path / "proj")


@pytest.fixture
def graph_project_id(graph_project: Path) -> str:
    return _project_svc._project_id(graph_project.resolve())


@pytest.fixture
def empty_client(graph_project: Path) -> TestClient:
    _project_svc.seed_project_index([graph_project])
    summary = _project_svc._try_load_summary(graph_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])
    return TestClient(create_app(dev_mode=True))


@pytest.fixture
def populated_client(
    graph_project: Path,
    save_test_issue,
    save_test_node,
) -> TestClient:
    _project_svc.seed_project_index([graph_project])
    summary = _project_svc._try_load_summary(graph_project.resolve())
    if summary is not None:
        _project_svc._discovery_cache = (time.monotonic(), [summary])

    save_test_node(graph_project, "user-model", type="model", status="active")
    save_test_issue(graph_project, "KUI-1", status="todo")
    save_test_issue(
        graph_project,
        "KUI-2",
        status="in_progress",
        blocked_by=["KUI-1"],
    )
    return TestClient(create_app(dev_mode=True))


class TestDepsGraphEmpty:
    def test_empty_project_returns_empty_graph_200(
        self,
        empty_client,
        graph_project_id,
    ):
        r = empty_client.get(f"/api/projects/{graph_project_id}/graph/deps")
        assert r.status_code == 200
        body = r.json()
        assert body["nodes"] == []
        assert body["edges"] == []
        assert body["meta"]["kind"] == "deps"


class TestDepsGraphPopulated:
    def test_returns_nodes_and_edges(self, populated_client, graph_project_id):
        r = populated_client.get(f"/api/projects/{graph_project_id}/graph/deps")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["kind"] == "deps"
        ids = {n["id"] for n in body["nodes"]}
        assert {"KUI-1", "KUI-2"}.issubset(ids)
        # KUI-2 blocked_by KUI-1 — there should be an edge.
        assert body["meta"]["edge_count"] >= 1


class TestDepsGraphDepthClamp:
    def test_large_depth_clamps_to_10_with_header(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/deps",
            params={"depth": 99},
        )
        assert r.status_code == 200
        assert r.headers.get("X-Tripwire-Clamp") == "depth"

    def test_depth_at_max_no_clamp_header(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/deps",
            params={"depth": 10},
        )
        assert "X-Tripwire-Clamp" not in r.headers


class TestDepsGraphMalformedFocus:
    def test_malformed_focus_returns_400(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/deps",
            params={"focus": "not a key!"},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "graph/bad_focus"

    def test_valid_issue_focus(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/deps",
            params={"focus": "KUI-1"},
        )
        assert r.status_code == 200


class TestConceptGraph:
    def test_empty_project(self, empty_client, graph_project_id):
        r = empty_client.get(f"/api/projects/{graph_project_id}/graph/concept")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["kind"] == "concept"

    def test_populated(self, populated_client, graph_project_id):
        r = populated_client.get(f"/api/projects/{graph_project_id}/graph/concept")
        assert r.status_code == 200
        body = r.json()
        assert body["meta"]["kind"] == "concept"

    def test_upstream_and_downstream_with_focus(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/concept",
            params={"focus": "KUI-2", "upstream": True, "downstream": True},
        )
        assert r.status_code == 200

    def test_malformed_focus_returns_400(
        self,
        populated_client,
        graph_project_id,
    ):
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/concept",
            params={"focus": "bad focus!"},
        )
        assert r.status_code == 400


class TestPatchConceptLayout:
    """Batched layout PATCH that writes through `.tripwire/concept-layout.json`."""

    def test_persists_batch_to_sidecar(
        self, populated_client, graph_project, graph_project_id
    ):
        from tripwire.core.concept_layout import load_concept_layouts

        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={
                "user-model": {"x": 100.0, "y": 200.0},
                "another-node": {"x": -5.5, "y": 0.0},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["layouts"]["user-model"] == {"x": 100.0, "y": 200.0}
        assert body["layouts"]["another-node"] == {"x": -5.5, "y": 0.0}

        on_disk = load_concept_layouts(graph_project)
        assert on_disk["user-model"] == (100.0, 200.0)
        assert on_disk["another-node"] == (-5.5, 0.0)

    def test_does_not_write_to_node_yaml(
        self, populated_client, graph_project, graph_project_id
    ):
        # The whole point: layout updates must not modify content YAML.
        node_path = graph_project / "nodes" / "user-model.yaml"
        before = node_path.read_text(encoding="utf-8")
        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={"user-model": {"x": 1.0, "y": 2.0}},
        )
        assert r.status_code == 200
        after = node_path.read_text(encoding="utf-8")
        assert before == after
        assert "layout:" not in after

    def test_partial_body_merges_with_existing(
        self, populated_client, graph_project, graph_project_id
    ):
        from tripwire.core.concept_layout import (
            load_concept_layouts,
            save_concept_layouts,
        )

        save_concept_layouts(
            graph_project, {"user-model": (10.0, 20.0), "kept": (3.0, 4.0)}
        )
        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={"user-model": {"x": 99.0, "y": 99.0}},
        )
        assert r.status_code == 200
        merged = load_concept_layouts(graph_project)
        assert merged == {"user-model": (99.0, 99.0), "kept": (3.0, 4.0)}

    def test_empty_body_is_a_noop_200(
        self, populated_client, graph_project, graph_project_id
    ):
        from tripwire.core.concept_layout import save_concept_layouts

        save_concept_layouts(graph_project, {"user-model": (10.0, 20.0)})
        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={},
        )
        assert r.status_code == 200
        assert r.json()["layouts"]["user-model"] == {"x": 10.0, "y": 20.0}

    def test_malformed_slug_returns_400(
        self, populated_client, graph_project_id
    ):
        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={"BadSlug": {"x": 1.0, "y": 2.0}},
        )
        assert r.status_code == 400
        assert r.json()["code"] == "node/bad_slug"

    def test_missing_y_returns_422(
        self, populated_client, graph_project_id
    ):
        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={"user-model": {"x": 1.0}},
        )
        assert r.status_code == 422

    def test_unknown_node_id_is_accepted(
        self, populated_client, graph_project, graph_project_id
    ):
        # Sidecar entries don't need to correspond to extant node YAMLs;
        # the file watcher won't ever see this and orphans are harmless
        # (a missing node just doesn't render, the position is kept).
        from tripwire.core.concept_layout import load_concept_layouts

        r = populated_client.patch(
            f"/api/projects/{graph_project_id}/graph/concept/layout",
            json={"never-existed": {"x": 1.0, "y": 2.0}},
        )
        assert r.status_code == 200
        assert load_concept_layouts(graph_project)["never-existed"] == (1.0, 2.0)


class TestConceptGraphReadsFromSidecar:
    def test_has_saved_layout_flag_reflects_sidecar(
        self, populated_client, graph_project, graph_project_id
    ):
        from tripwire.core.concept_layout import save_concept_layouts

        save_concept_layouts(graph_project, {"user-model": (42.0, 84.0)})
        r = populated_client.get(
            f"/api/projects/{graph_project_id}/graph/concept"
        )
        assert r.status_code == 200
        body = r.json()
        target = next(n for n in body["nodes"] if n["id"] == "user-model")
        assert target["data"]["has_saved_layout"] is True
        assert target["position"] == {"x": 42.0, "y": 84.0}


class TestOpenAPI:
    def test_registers_paths(self, populated_client):
        schema = populated_client.get("/openapi.json").json()
        paths = schema["paths"]
        assert "/api/projects/{project_id}/graph/deps" in paths
        assert "/api/projects/{project_id}/graph/concept" in paths
        assert "/api/projects/{project_id}/graph/concept/layout" in paths
