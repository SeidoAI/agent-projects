"""``tripwire workspace`` — workspace lifecycle, link, and node sync.

This package replaces the former single-file ``cli/workspace.py``. The
Click group itself is defined in :mod:`tripwire.cli.workspace._group`;
each subcommand lives in its own module and registers itself on the
group at import time via ``@workspace_cmd.command(...)``. Shared helpers
live in :mod:`tripwire.cli.workspace._helpers`.

Subcommands (one per module):

- ``init`` — bootstrap a new workspace
- ``link <path>`` — register current project with a workspace
- ``unlink [--force]`` — remove the project's workspace link
- ``list`` — enumerate registered projects
- ``status`` — sync state (workspace-side or project-side)
- ``prune [--force]`` — remove orphan project entries
- ``copy <node-id>...`` — import workspace nodes into project
- ``pull [--nodes] [--dry-run]`` — refresh workspace-origin nodes
- ``push [--nodes] [--dry-run]`` — send local node changes up
- ``fork <node-id>`` — detach a workspace-origin node from sync
- ``promote <node-id>`` — flip local node scope=workspace + push
- ``merge-resolve <node-id>`` — finalize an agent-resolved merge
"""

from __future__ import annotations

from tripwire.cli.workspace import copy as _copy_mod  # noqa: F401
from tripwire.cli.workspace import fork as _fork_mod  # noqa: F401

# Subcommand modules: imported here purely for their side effect of
# registering ``@workspace_cmd.command(...)`` on the group. Order
# matches the original cli/workspace.py declaration order so ``--help``
# remains stable (though Click sorts alphabetically anyway).
from tripwire.cli.workspace import init as _init_mod  # noqa: F401
from tripwire.cli.workspace import link as _link_mod  # noqa: F401
from tripwire.cli.workspace import list as _list_mod  # noqa: F401
from tripwire.cli.workspace import merge_resolve as _merge_resolve_mod  # noqa: F401
from tripwire.cli.workspace import promote as _promote_mod  # noqa: F401
from tripwire.cli.workspace import prune as _prune_mod  # noqa: F401
from tripwire.cli.workspace import pull as _pull_mod  # noqa: F401
from tripwire.cli.workspace import push as _push_mod  # noqa: F401
from tripwire.cli.workspace import status as _status_mod  # noqa: F401
from tripwire.cli.workspace import unlink as _unlink_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.workspace._group import workspace_cmd

__all__ = ["workspace_cmd"]
