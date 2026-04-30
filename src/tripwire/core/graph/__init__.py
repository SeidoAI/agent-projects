"""Graph subsystem package.

The flat modules `core/graph_cache.py`, `core/concept_graph.py`,
`core/dependency_graph.py`, `core/reference_parser.py` were consolidated
under `core/graph/` in v0.9 (KUI-131). This package re-exports their
public APIs so existing call sites (`from tripwire.core.graph_cache
import …`) keep working via shim modules at the old paths.

New code should import from the package modules directly:

    from tripwire.core.graph import cache, concept, dependency, refs
"""

from __future__ import annotations

from tripwire.core.graph import cache, concept, dependency, edges, index, refs

__all__ = ["cache", "concept", "dependency", "edges", "index", "refs"]
