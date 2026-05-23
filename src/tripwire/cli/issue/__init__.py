"""``tripwire issue`` — per-issue operations (artifact, insights).

v0.7b introduces per-issue artifacts (developer.md, verified.md) alongside
the issue YAML. This module exposes the read/render/verify helpers; the
PM slash command `/pm-issue-artifact` drives it.

This package replaces the former single-file ``cli/issue.py``. The
Click group itself is defined in :mod:`tripwire.cli.issue._group`; each
subcommand lives in its own module and registers itself on the group at
import time via ``@issue_cmd.command(...)`` or
``@issue_cmd.group(...)``.

Subcommands:

- ``artifact`` — sub-group: ``list``, ``init``, ``verify`` per-issue
  artifact manifest operations
"""

from __future__ import annotations

# Subcommand modules: imported here purely for their side effect of
# registering ``@issue_cmd.command(...)`` (and nested sub-groups) on
# the group. Order matches the original cli/issue.py declaration order.
from tripwire.cli.issue import artifact as _artifact_mod  # noqa: F401

# Bare group first — every subcommand module imports it.
from tripwire.cli.issue._group import issue_cmd

__all__ = ["issue_cmd"]
