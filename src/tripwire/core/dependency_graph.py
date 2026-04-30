"""Backward-compat shim: re-exports from `tripwire.core.graph.dependency`.

Moved in v0.9 (KUI-131). New code should import from
`tripwire.core.graph.dependency` directly.
"""

from __future__ import annotations

from tripwire.core.graph.dependency import *  # noqa: F403
from tripwire.core.graph.dependency import (  # noqa: F401
    build_dependency_graph,
    to_dot,
    to_mermaid,
)
