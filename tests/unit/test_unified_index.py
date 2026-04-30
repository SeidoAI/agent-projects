"""Unit tests for the unified entity-graph index (KUI-131 / A6).

The unified index is the canonical view over every entity type in a project
(concept-node, issue, session, decision, comment, pull-request,
tripwire-instance) and every entity-to-entity edge kind (refs, depends_on,
implements, produced-by, supersedes, addressed-by, tripwire-fired-on).

These tests pin the schema additions and the public API of the new
`core.graph.index` facade.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.graph import index as graph_index
from tripwire.models.graph import (
    EdgeKind,
    GraphEdge,
    GraphIndex,
    GraphNode,
    NodeKind,
)


class TestEdgeKindEnum:
    """The 7 canonical edge kinds named in the v0.9 plan must exist."""

    def test_all_seven_kinds_present(self):
        kinds = {k.value for k in EdgeKind}
        assert kinds == {
            "refs",
            "depends_on",
            "implements",
            "produced-by",
            "supersedes",
            "addressed-by",
            "tripwire-fired-on",
        }


class TestNodeKindEnum:
    """The 7 canonical node kinds named in the v0.9 plan must exist."""

    def test_all_seven_kinds_present(self):
        kinds = {k.value for k in NodeKind}
        assert kinds == {
            "concept-node",
            "issue",
            "session",
            "decision",
            "comment",
            "pull-request",
            "tripwire-instance",
        }


class TestGraphEdgeNewFields:
    """v0.9 adds optional `via_artifact` and `line` fields to GraphEdge.

    Per-edge provenance: `via_artifact` names the file (or other artifact)
    that produced the edge; `line` pins the line number for body refs.
    """

    def test_via_artifact_and_line_default_to_none(self):
        e = GraphEdge(from_id="a", to_id="b", type="refs")
        assert e.via_artifact is None
        assert e.line is None

    def test_via_artifact_and_line_round_trip(self):
        e = GraphEdge(
            from_id="a",
            to_id="b",
            type="refs",
            via_artifact="issues/KUI-1/issue.yaml",
            line=42,
        )
        assert e.via_artifact == "issues/KUI-1/issue.yaml"
        assert e.line == 42
        # round-trip via dict (alias mode is what graph cache writes)
        dumped = e.model_dump(mode="json", by_alias=True, exclude_none=True)
        revived = GraphEdge.model_validate(dumped)
        assert revived.via_artifact == "issues/KUI-1/issue.yaml"
        assert revived.line == 42


class TestLegacyEdgeMapping:
    """Legacy edge type strings are mapped onto canonical EdgeKind values.

    Backward-compat: existing graph/index.yaml uses legacy strings
    (`references`, `blocked_by`, `related`). The mapping lets the unified
    facade query them under the new canonical names.
    """

    @pytest.mark.parametrize(
        ("legacy", "canonical"),
        [
            ("references", "refs"),
            ("related", "refs"),
            ("blocked_by", "depends_on"),
            ("implements", "implements"),
        ],
    )
    def test_legacy_to_canonical(self, legacy, canonical):
        assert graph_index.canonical_kind(legacy) == canonical

    def test_unknown_kind_passes_through(self):
        # Forward-compat: an unrecognised type string is returned unchanged
        # rather than raising. This keeps a stale agent that ships a new
        # edge kind from poisoning every read of the index.
        assert graph_index.canonical_kind("future_kind") == "future_kind"


class TestUnifiedIndexFacade:
    """`UnifiedIndex` provides per-type and per-kind queries."""

    def _build_cache(self) -> GraphIndex:
        cache = GraphIndex(version=2)
        cache.edges = [
            GraphEdge(from_id="KUI-1", to_id="user-model", type="references"),
            GraphEdge(from_id="KUI-1", to_id="KUI-2", type="blocked_by"),
            GraphEdge(from_id="KUI-3", to_id="KUI-1", type="implements"),
        ]
        return cache

    def test_edges_by_canonical_kind_translates_legacy(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        # `references` is legacy for `refs`
        refs = idx.edges_by_kind("refs")
        assert len(refs) == 1
        assert refs[0].to_id == "user-model"

    def test_edges_by_canonical_kind_depends_on(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        # `blocked_by` is legacy for `depends_on`
        deps = idx.edges_by_kind("depends_on")
        assert len(deps) == 1
        assert deps[0].from_id == "KUI-1"
        assert deps[0].to_id == "KUI-2"

    def test_edges_into(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        incoming = idx.edges_into("KUI-1")
        # KUI-3 implements KUI-1 => one incoming
        assert len(incoming) == 1
        assert incoming[0].from_id == "KUI-3"

    def test_edges_from(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        outgoing = idx.edges_from("KUI-1")
        # references user-model + blocked_by KUI-2 => two outgoing
        assert len(outgoing) == 2

    def test_upstream_and_downstream(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        # upstream of KUI-1: things KUI-1 references / depends on
        # => user-model, KUI-2
        up = set(idx.upstream("KUI-1"))
        assert up == {"user-model", "KUI-2"}
        # downstream of KUI-1: things that point at KUI-1
        # => KUI-3 (implements)
        down = set(idx.downstream("KUI-1"))
        assert down == {"KUI-3"}

    def test_upstream_with_kind_filter(self):
        idx = graph_index.UnifiedIndex(
            project_dir=Path("/tmp/proj"),
            cache=self._build_cache(),
        )
        # KUI-1 has refs (-> user-model) and depends_on (-> KUI-2).
        # Filter to refs only.
        up = set(idx.upstream("KUI-1", kinds=["refs"]))
        assert up == {"user-model"}

    def test_distance_2_transitive_closure(self):
        cache = GraphIndex(version=2)
        cache.edges = [
            GraphEdge(from_id="A", to_id="B", type="references"),
            GraphEdge(from_id="B", to_id="C", type="references"),
        ]
        idx = graph_index.UnifiedIndex(project_dir=Path("/tmp/proj"), cache=cache)
        up_d1 = set(idx.upstream("A", distance=1))
        up_d2 = set(idx.upstream("A", distance=2))
        assert up_d1 == {"B"}
        assert up_d2 == {"B", "C"}


class TestBackwardsCompatLoad:
    """Existing graph/index.yaml YAML must continue to load cleanly."""

    def test_legacy_index_round_trips(self):
        """A v2-shape cache (no via_artifact/line) loads and re-dumps."""
        legacy = {
            "version": 2,
            "files": {},
            "edges": [
                {"from": "KUI-1", "to": "user-model", "type": "references"},
            ],
        }
        idx = GraphIndex.model_validate(legacy)
        assert len(idx.edges) == 1
        # The `via_artifact` field should be present and None
        assert idx.edges[0].via_artifact is None


class TestGraphNodeKindLooseString:
    """GraphNode.kind stays str (loose) for backward compat.

    Existing on-disk YAML uses kind="issue" / kind="node"; the schema
    must keep accepting those without raising. NodeKind exists for new
    code that wants the canonical names; the model field stays loose.
    """

    def test_legacy_kinds_load(self):
        assert GraphNode(id="x", kind="issue")
        assert GraphNode(id="x", kind="node")
        # And the new canonical names also load
        assert GraphNode(id="x", kind="concept-node")
        assert GraphNode(id="x", kind="session")
