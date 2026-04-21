"""Tests for tripwire.ui.services.graph_service."""

from __future__ import annotations

import json
from pathlib import Path

from tripwire.ui.services.graph_service import (
    ReactFlowEdge,
    ReactFlowGraph,
    ReactFlowNode,
    build_concept_graph,
    build_dependency_graph,
    current_cache_version,
)

# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


class TestBuildDependencyGraph:
    def test_empty_project(self, tmp_path_project: Path):
        g = build_dependency_graph(tmp_path_project)
        assert isinstance(g, ReactFlowGraph)
        assert g.nodes == []
        assert g.edges == []
        assert g.meta.kind == "deps"
        assert g.meta.node_count == 0

    def test_basic_blocked_by_graph(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"])
        save_test_issue(tmp_path_project, "TST-3", blocked_by=["TST-2"])

        g = build_dependency_graph(tmp_path_project)

        ids = {n.id for n in g.nodes}
        assert ids == {"TST-1", "TST-2", "TST-3"}

        # All edges carry relation = "blocked_by"
        assert all(e.relation == "blocked_by" for e in g.edges)

        # Edge set: TST-2 → TST-1 and TST-3 → TST-2
        edge_pairs = {(e.source, e.target) for e in g.edges}
        assert edge_pairs == {("TST-2", "TST-1"), ("TST-3", "TST-2")}

        # Each node has required React Flow fields.
        for n in g.nodes:
            assert isinstance(n, ReactFlowNode)
            assert n.type in {"issue", "concept"}
            assert n.position is not None
            assert n.data["label"]

    def test_deterministic_positions(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"])

        g1 = build_dependency_graph(tmp_path_project)
        g2 = build_dependency_graph(tmp_path_project)

        pos1 = {n.id: (n.position.x, n.position.y) for n in g1.nodes}
        pos2 = {n.id: (n.position.x, n.position.y) for n in g2.nodes}
        assert pos1 == pos2

    def test_focus_upstream_restricts(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"])
        save_test_issue(tmp_path_project, "TST-3", blocked_by=["TST-2"])
        save_test_issue(tmp_path_project, "TST-4")  # unrelated

        # Upstream of TST-2 = {TST-2, TST-1}
        g = build_dependency_graph(tmp_path_project, focus="TST-2", upstream=True)
        ids = {n.id for n in g.nodes}
        assert ids == {"TST-1", "TST-2"}

    def test_focus_downstream_restricts(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"])
        save_test_issue(tmp_path_project, "TST-3", blocked_by=["TST-2"])

        # Downstream of TST-2 = {TST-2, TST-3}
        g = build_dependency_graph(tmp_path_project, focus="TST-2", downstream=True)
        ids = {n.id for n in g.nodes}
        assert ids == {"TST-2", "TST-3"}

    def test_focus_unknown_returns_empty(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        g = build_dependency_graph(tmp_path_project, focus="TST-99", upstream=True)
        # Selector raises ValueError internally → empty focus set → no nodes.
        assert g.nodes == []

    def test_edges_have_stable_ids(self, tmp_path_project: Path, save_test_issue):
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"])

        g1 = build_dependency_graph(tmp_path_project)
        g2 = build_dependency_graph(tmp_path_project)
        assert [e.id for e in g1.edges] == [e.id for e in g2.edges]


# ---------------------------------------------------------------------------
# Concept graph
# ---------------------------------------------------------------------------


class TestBuildConceptGraph:
    def test_empty_project(self, tmp_path_project: Path):
        g = build_concept_graph(tmp_path_project)
        assert g.nodes == []
        assert g.edges == []
        assert g.meta.kind == "concept"

    def test_returns_issues_and_nodes(
        self, tmp_path_project: Path, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        g = build_concept_graph(tmp_path_project)
        ids = {n.id for n in g.nodes}
        assert "user-model" in ids
        assert "TST-1" in ids

    def test_edge_relations_cover_types(
        self, tmp_path_project: Path, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")
        save_test_issue(tmp_path_project, "TST-2", blocked_by=["TST-1"], parent="TST-1")

        g = build_concept_graph(tmp_path_project)
        relations = {e.relation for e in g.edges}
        assert "references" in relations  # TST-* body has [[user-model]]
        assert "blocked_by" in relations
        assert "parent" in relations

    def test_react_flow_shape_complies(
        self, tmp_path_project: Path, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        g = build_concept_graph(tmp_path_project)
        for n in g.nodes:
            assert hasattr(n, "id") and hasattr(n, "position") and hasattr(n, "type")
            assert n.position.x is not None and n.position.y is not None
        for e in g.edges:
            assert isinstance(e, ReactFlowEdge)
            assert e.source and e.target
            assert e.relation

    def test_focus_upstream_on_concept_graph(
        self, tmp_path_project: Path, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")  # references user-model

        g = build_concept_graph(tmp_path_project, focus="TST-1", upstream=True)
        ids = {n.id for n in g.nodes}
        # Upstream of TST-1 includes TST-1 and what it references.
        assert "TST-1" in ids
        assert "user-model" in ids

    def test_dto_round_trips_via_json(
        self, tmp_path_project: Path, save_test_issue, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        save_test_issue(tmp_path_project, "TST-1")

        g = build_concept_graph(tmp_path_project)
        rebuilt = ReactFlowGraph.model_validate(json.loads(g.model_dump_json()))
        assert rebuilt == g


# ---------------------------------------------------------------------------
# Cache-version helper
# ---------------------------------------------------------------------------


class TestCurrentCacheVersion:
    def test_none_when_cache_missing(self, tmp_path_project: Path):
        assert current_cache_version(tmp_path_project) is None

    def test_returns_iso_timestamp_after_rebuild(
        self, tmp_path_project: Path, save_test_node
    ):
        save_test_node(tmp_path_project, "user-model")
        from tripwire.core import graph_cache

        graph_cache.full_rebuild(tmp_path_project)
        v = current_cache_version(tmp_path_project)
        assert v is not None
        # Should be an ISO-like timestamp with T separator.
        assert "T" in v
