"""Unit tests for upstream/downstream graph navigation (F10)."""

from __future__ import annotations

import click
import pytest

from tripwire.cli.graph import _bfs_reachable, _filter_graph_by_direction
from tripwire.models.graph import FullGraphResult, GraphEdge, GraphNode


def _make_graph() -> FullGraphResult:
    """Build a 5-node graph:

        A → B → C
        A → D
        E (orphan)

    Edge semantics: from_id references/depends-on to_id.
    So A references B, A references D, B references C.
    """
    return FullGraphResult(
        nodes=[
            GraphNode(id="A", kind="node"),
            GraphNode(id="B", kind="node"),
            GraphNode(id="C", kind="node"),
            GraphNode(id="D", kind="node"),
            GraphNode(id="E", kind="node"),
        ],
        edges=[
            GraphEdge(from_id="A", to_id="B", type="references"),
            GraphEdge(from_id="B", to_id="C", type="references"),
            GraphEdge(from_id="A", to_id="D", type="references"),
        ],
    )


class TestBfsReachable:
    def test_from_root(self) -> None:
        adj = {"A": {"B", "D"}, "B": {"C"}}
        assert _bfs_reachable("A", adj) == {"A", "B", "C", "D"}

    def test_from_leaf(self) -> None:
        adj = {"A": {"B", "D"}, "B": {"C"}}
        assert _bfs_reachable("C", adj) == {"C"}

    def test_from_middle(self) -> None:
        adj = {"A": {"B", "D"}, "B": {"C"}}
        assert _bfs_reachable("B", adj) == {"B", "C"}


class TestFilterGraphByDirection:
    def test_upstream_from_A(self) -> None:
        """Upstream of A = A + everything A references transitively."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id="A", downstream_id=None)
        ids = {n.id for n in g.nodes}
        assert ids == {"A", "B", "C", "D"}
        assert len(g.edges) == 3

    def test_upstream_from_B(self) -> None:
        """Upstream of B = B + C (what B references)."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id="B", downstream_id=None)
        ids = {n.id for n in g.nodes}
        assert ids == {"B", "C"}
        assert len(g.edges) == 1

    def test_upstream_from_leaf(self) -> None:
        """Upstream of C = just C (leaf)."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id="C", downstream_id=None)
        ids = {n.id for n in g.nodes}
        assert ids == {"C"}
        assert len(g.edges) == 0

    def test_downstream_from_C(self) -> None:
        """Downstream of C = C + B + A (who references C transitively)."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id=None, downstream_id="C")
        ids = {n.id for n in g.nodes}
        assert ids == {"A", "B", "C"}
        assert len(g.edges) == 2  # A→B, B→C

    def test_downstream_from_D(self) -> None:
        """Downstream of D = D + A (only A references D)."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id=None, downstream_id="D")
        ids = {n.id for n in g.nodes}
        assert ids == {"A", "D"}

    def test_downstream_from_orphan(self) -> None:
        """Downstream of E = just E (orphan, no referrers)."""
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id=None, downstream_id="E")
        ids = {n.id for n in g.nodes}
        assert ids == {"E"}
        assert len(g.edges) == 0

    def test_noop_when_no_filter(self) -> None:
        g = _make_graph()
        _filter_graph_by_direction(g, upstream_id=None, downstream_id=None)
        assert len(g.nodes) == 5
        assert len(g.edges) == 3

    def test_unknown_id_raises(self) -> None:
        g = _make_graph()
        with pytest.raises(click.ClickException, match="not found"):
            _filter_graph_by_direction(g, upstream_id="NOPE", downstream_id=None)
