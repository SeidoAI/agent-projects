"""``tripwire pr`` — PR-side operations.

This package replaces the former single-file ``cli/pr.py``. The
Click group itself is defined in :mod:`tripwire.cli.pr._group`; each
subcommand lives in its own module and registers itself on the group
at import time via ``@pr_cmd.command(...)``.

Subcommands (one per module):

- ``status <session-id>`` — latest pm-review verdict for a session
- ``summary`` — render a PR comment for a base..head diff
- ``watch`` — post-PR auto-check daemon (start/status/stop/logs)
"""

from __future__ import annotations

# Subcommand modules: imported here purely for their side effect of
# registering ``@pr_cmd.command(...)`` on the group.
from tripwire.cli.pr import status as _status_mod  # noqa: F401
from tripwire.cli.pr import summary as _summary_mod  # noqa: F401
from tripwire.cli.pr import watch as _watch_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.pr._group import pr_cmd
from tripwire.cli.pr.status import pr_status_cmd
from tripwire.cli.pr.summary import pr_summary_cmd
from tripwire.cli.pr.watch import watch_cmd

__all__ = [
    "pr_cmd",
    "pr_status_cmd",
    "pr_summary_cmd",
    "watch_cmd",
]
