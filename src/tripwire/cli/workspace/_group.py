"""Bare ``workspace`` Click group definition.

Lives in its own module so each subcommand file under ``cli/workspace/``
can ``from tripwire.cli.workspace._group import workspace_cmd`` without
pulling in (and circularly importing) the subcommand modules registered
in ``cli/workspace/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="workspace")
def workspace_cmd() -> None:
    """Workspace operations: init, link, sync, copy, pull/push/merge-resolve."""
