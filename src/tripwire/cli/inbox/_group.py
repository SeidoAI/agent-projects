"""Bare ``inbox`` Click group definition.

Lives in its own module so each subcommand file under ``cli/inbox/`` can
``from tripwire.cli.inbox._group import inbox_cmd`` without pulling in
(and circularly importing) the subcommand modules registered in
``cli/inbox/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="inbox")
def inbox_cmd() -> None:
    """Inspect the PM-agent attention queue."""
