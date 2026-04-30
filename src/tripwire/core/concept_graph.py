"""Backward-compat shim: re-exports from `tripwire.core.graph.concept`.

Moved in v0.9 (KUI-131). New code should import from
`tripwire.core.graph.concept` directly.
"""

from __future__ import annotations

from tripwire.core.graph.concept import *  # noqa: F403
from tripwire.core.graph.concept import (  # noqa: F401
    build_full_graph,
    orphan_issues,
    orphan_nodes,
)
