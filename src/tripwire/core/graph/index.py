"""Unified entity-graph index (KUI-131 / A6).

The unified index is the canonical view over every entity type in a
project (concept-node, issue, session, decision, comment, pull-request,
tripwire-instance) and every entity-to-entity edge kind (refs,
depends_on, implements, produced-by, supersedes, addressed-by,
tripwire-fired-on).

It sits on top of :class:`tripwire.models.graph.GraphIndex` (the
on-disk cache schema, which keeps using legacy edge type strings for
backward compatibility) and exposes a per-kind / per-type query
surface to the new `tripwire graph query` CLI, the validator, and the
drift report.

The legacy `core.graph.concept` and `core.graph.dependency` modules
keep their public APIs but read through this facade — there is no
duplicate state.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from tripwire.core.graph import cache as graph_cache
from tripwire.core.graph import edges as graph_edges
from tripwire.models.graph import EdgeKind, GraphEdge, GraphIndex


# ---------------------------------------------------------------------------
# Legacy → canonical edge-kind mapping
# ---------------------------------------------------------------------------

# Keys are the legacy strings actually stored in `graph/index.yaml`.
# Values are the canonical EdgeKind values (KUI-131's 7-kind taxonomy).
_LEGACY_TO_CANONICAL: dict[str, str] = {
    "references": EdgeKind.REFS.value,
    "related": EdgeKind.REFS.value,
    "refs": EdgeKind.REFS.value,
    "blocked_by": EdgeKind.DEPENDS_ON.value,
    "depends_on": EdgeKind.DEPENDS_ON.value,
    "implements": EdgeKind.IMPLEMENTS.value,
    "produced-by": EdgeKind.PRODUCED_BY.value,
    "supersedes": EdgeKind.SUPERSEDES.value,
    "addressed-by": EdgeKind.ADDRESSED_BY.value,
    "tripwire-fired-on": EdgeKind.TRIPWIRE_FIRED_ON.value,
}


def canonical_kind(edge_type: str) -> str:
    """Return the canonical :class:`EdgeKind` value for a legacy edge string.

    Unknown strings are returned unchanged — this is forward-compat: a
    stale agent that ships a new edge kind doesn't poison every read.
    """
    return _LEGACY_TO_CANONICAL.get(edge_type, edge_type)


# ---------------------------------------------------------------------------
# Unified index facade
# ---------------------------------------------------------------------------


class UnifiedIndex:
    """Read-only facade over a :class:`GraphIndex` for canonical queries.

    All edge-kind queries take the canonical name (e.g. ``"refs"``) and
    match across every legacy edge type that maps to that kind (e.g.
    both ``"references"`` and ``"related"`` count as ``"refs"``).

    This class never mutates the underlying cache; mutation goes
    through `core.graph.cache.update_cache_for_file` /
    `full_rebuild` exactly as before.
    """

    def __init__(self, project_dir: Path, cache: GraphIndex) -> None:
        self.project_dir = project_dir
        self._cache = cache

    # -- edge queries -----------------------------------------------------

    def edges_by_kind(self, kind: str) -> list[GraphEdge]:
        """All edges whose canonical kind matches `kind`."""
        return [e for e in self._cache.edges if canonical_kind(e.type) == kind]

    def edges_into(self, node_id: str) -> list[GraphEdge]:
        """All edges whose target is `node_id` (incoming)."""
        return [e for e in self._cache.edges if e.to_id == node_id]

    def edges_from(self, node_id: str) -> list[GraphEdge]:
        """All edges whose source is `node_id` (outgoing)."""
        return [e for e in self._cache.edges if e.from_id == node_id]

    def edges_by_inverse_kind(
        self, node_id: str, inverse_name: str
    ) -> list[tuple[str, str]]:
        """Surface edges into `node_id` under their *inverse* name.

        For example, ``edges_by_inverse_kind("KUI-1", "blocks")`` finds
        every ``depends_on`` edge into KUI-1 and returns the upstream
        node id paired with the original (canonical) kind name. The
        canonical-direction edges live on disk; the inverse name
        (``blocks``, ``implemented-by``, ``produces`` …) is computed at
        read time per the v0.6 ``blocked_by`` ↔ ``blocks`` convention.

        For bidirectional kinds (``refs``), incoming refs are returned
        with the same kind name on either side.

        Returns a list of ``(other_id, original_kind)`` tuples.
        """
        canonical = graph_edges.canonical_for_inverse(inverse_name)
        out: list[tuple[str, str]] = []
        for e in self._cache.edges:
            if e.to_id != node_id:
                continue
            if canonical_kind(e.type) == canonical:
                out.append((e.from_id, canonical))
        return out

    # -- traversal --------------------------------------------------------

    def upstream(
        self,
        node_id: str,
        *,
        kinds: Iterable[str] | None = None,
        distance: int = 1,
    ) -> list[str]:
        """IDs of nodes reachable from `node_id` via outgoing edges.

        `kinds` filters by canonical edge kind (e.g. ``["refs"]``).
        `distance` is the maximum hops; ``distance=1`` is direct
        neighbours, ``distance=2`` is one hop further, and so on.
        """
        return self._traverse(
            node_id,
            adjacency=self._outgoing_adjacency(kinds),
            distance=distance,
        )

    def downstream(
        self,
        node_id: str,
        *,
        kinds: Iterable[str] | None = None,
        distance: int = 1,
    ) -> list[str]:
        """IDs of nodes that reach `node_id` via outgoing edges (incoming)."""
        return self._traverse(
            node_id,
            adjacency=self._incoming_adjacency(kinds),
            distance=distance,
        )

    # -- internal ---------------------------------------------------------

    def _outgoing_adjacency(
        self, kinds: Iterable[str] | None
    ) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        wanted = set(kinds) if kinds else None
        for e in self._cache.edges:
            if wanted is not None and canonical_kind(e.type) not in wanted:
                continue
            adj[e.from_id].append(e.to_id)
        return adj

    def _incoming_adjacency(
        self, kinds: Iterable[str] | None
    ) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = defaultdict(list)
        wanted = set(kinds) if kinds else None
        for e in self._cache.edges:
            if wanted is not None and canonical_kind(e.type) not in wanted:
                continue
            adj[e.to_id].append(e.from_id)
        return adj

    @staticmethod
    def _traverse(
        start: str,
        adjacency: dict[str, list[str]],
        distance: int,
    ) -> list[str]:
        if distance < 1:
            return []
        seen: set[str] = set()
        frontier: list[str] = [start]
        for _ in range(distance):
            next_frontier: list[str] = []
            for current in frontier:
                for neighbour in adjacency.get(current, ()):
                    if neighbour == start or neighbour in seen:
                        continue
                    seen.add(neighbour)
                    next_frontier.append(neighbour)
            frontier = next_frontier
            if not frontier:
                break
        return sorted(seen)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def load(project_dir: Path) -> UnifiedIndex:
    """Load the unified index for `project_dir`.

    Falls back to an empty cache if `graph/index.yaml` is missing — the
    facade is still usable but will return empty queries. The caller
    can run `core.graph.cache.ensure_fresh` first if it wants to be
    sure the index reflects the current filesystem.
    """
    cache = graph_cache.load_index(project_dir)
    if cache is None:
        cache = GraphIndex(version=graph_cache.CACHE_VERSION)
    return UnifiedIndex(project_dir=project_dir, cache=cache)


__all__ = [
    "UnifiedIndex",
    "canonical_kind",
    "load",
]
