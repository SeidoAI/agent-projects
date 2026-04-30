"""Backward-compat shim: re-exports from `tripwire.core.graph.refs`.

Moved in v0.9 (KUI-131). New code should import from
`tripwire.core.graph.refs` directly.
"""

from __future__ import annotations

from tripwire.core.graph.refs import *  # noqa: F403
from tripwire.core.graph.refs import (  # noqa: F401
    FENCE_PATTERN,
    REFERENCE_PATTERN,
    extract_references,
    extract_references_with_pins,
    replace_references,
)
