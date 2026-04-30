"""Per-kind directionality semantics (KUI-134 / A9).

Every canonical edge kind has either a bidirectional rule (`refs`)
or a named inverse that the graph cache surfaces at read time. The
inverse is never stored on disk — that pattern matches the existing
`blocked_by` ↔ `blocks` convention from v0.6.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.graph import edges as graph_edges
from tripwire.core.graph.index import UnifiedIndex
from tripwire.models.graph import GraphEdge, GraphIndex


@pytest.mark.parametrize(
    ("kind", "inverse"),
    [
        ("refs", "refs"),
        ("depends_on", "blocks"),
        ("implements", "implemented-by"),
        ("produced-by", "produces"),
        ("supersedes", "superseded-by"),
        ("addressed-by", "addresses"),
        ("tripwire-fired-on", "fired-tripwires"),
    ],
)
def test_inverse_kind(kind, inverse):
    assert graph_edges.inverse_kind(kind) == inverse


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("refs", True),
        ("depends_on", False),
        ("implements", False),
        ("produced-by", False),
        ("supersedes", False),
        ("addressed-by", False),
        ("tripwire-fired-on", False),
    ],
)
def test_is_bidirectional(kind, expected):
    assert graph_edges.is_bidirectional(kind) is expected


def test_inverse_kind_roundtrips():
    """Inverse-of-inverse returns the original kind for every directional kind."""
    for kind in (
        "depends_on",
        "implements",
        "produced-by",
        "supersedes",
        "addressed-by",
        "tripwire-fired-on",
    ):
        inv = graph_edges.inverse_kind(kind)
        assert graph_edges.inverse_kind(inv) == kind


def test_inverse_kind_unknown_passes_through():
    # Forward-compat: unknown strings return themselves rather than raising.
    assert graph_edges.inverse_kind("future_kind") == "future_kind"


class TestUnifiedIndexInverseQuery:
    def _cache(self) -> GraphIndex:
        cache = GraphIndex(version=2)
        cache.edges = [
            GraphEdge(from_id="KUI-2", to_id="KUI-1", type="blocked_by"),
            GraphEdge(from_id="KUI-3", to_id="KUI-1", type="implements"),
            GraphEdge(from_id="comment-1", to_id="KUI-1", type="references"),
        ]
        return cache

    def test_edges_by_inverse_kind_blocks(self):
        idx = UnifiedIndex(project_dir=Path("/tmp/proj"), cache=self._cache())
        # `blocks` is the inverse of `depends_on`. KUI-2 depends on
        # KUI-1, so KUI-1 blocks KUI-2 — querying by kind=blocks at
        # KUI-1 should surface the edge.
        blockers = idx.edges_by_inverse_kind("KUI-1", "blocks")
        # Returned as (other_id, original_edge_kind) tuples for clarity.
        assert ("KUI-2", "depends_on") in blockers

    def test_edges_by_inverse_kind_implemented_by(self):
        idx = UnifiedIndex(project_dir=Path("/tmp/proj"), cache=self._cache())
        implementers = idx.edges_by_inverse_kind("KUI-1", "implemented-by")
        assert ("KUI-3", "implements") in implementers

    def test_edges_by_inverse_kind_refs_is_bidirectional(self):
        """For bidirectional kinds, inverse query returns both sides."""
        idx = UnifiedIndex(project_dir=Path("/tmp/proj"), cache=self._cache())
        # `refs` is bidirectional — querying inverse-of-refs at KUI-1
        # should still return the comment that references it.
        refs = idx.edges_by_inverse_kind("KUI-1", "refs")
        assert ("comment-1", "refs") in refs
