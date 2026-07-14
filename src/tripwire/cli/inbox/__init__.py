"""``tripwire inbox`` — read-only inspection of the PM-agent attention queue.

Authoring stays in YAML (the PM agent writes inbox/<id>.md directly,
matching the existing "agents create entities by writing files" rule).
Resolving lives in the dashboard UI. The CLI is purely a way to
inspect the queue from a terminal.

This package replaces the former single-file ``cli/inbox.py``. The
Click group itself is defined in :mod:`tripwire.cli.inbox._group`; each
subcommand lives in its own module and registers itself on the group
at import time via ``@inbox_cmd.command(...)``.

Subcommands:

- ``list`` — enumerate inbox entries (filterable by bucket / resolved)
- ``show <entry_id>`` — show one inbox entry by id
"""

from __future__ import annotations

# Subcommand modules: imported here purely for their side effect of
# registering ``@inbox_cmd.command(...)`` on the group. Order matches
# the original cli/inbox.py declaration order.
from tripwire.cli.inbox import list as _list_mod  # noqa: F401
from tripwire.cli.inbox import show as _show_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.inbox._group import inbox_cmd

__all__ = ["inbox_cmd"]
