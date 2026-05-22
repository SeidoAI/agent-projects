"""``tripwire node`` — concept node operations.

This package replaces the former single-file ``cli/node.py``. The
Click group itself is defined in :mod:`tripwire.cli.node._group`;
each subcommand lives in its own module and registers itself on the
group at import time.

Subcommands (one per module):

- ``check [<node-id>]`` — freshness check (one or all)
- ``refs <subs>`` — reference inspection (list, reverse, check, summary)
- ``graph <subs>`` — render or query the unified entity graph
"""

from __future__ import annotations

# Subcommand modules: imported for their side effect of registering on
# the group.
from tripwire.cli.node import check as _check_mod  # noqa: F401
from tripwire.cli.node import graph as _graph_mod  # noqa: F401
from tripwire.cli.node import refs as _refs_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.node._group import node_cmd
from tripwire.cli.node.check import node_check_cmd
from tripwire.cli.node.graph import graph_cmd
from tripwire.cli.node.refs import refs_cmd

__all__ = [
    "graph_cmd",
    "node_check_cmd",
    "node_cmd",
    "refs_cmd",
]
