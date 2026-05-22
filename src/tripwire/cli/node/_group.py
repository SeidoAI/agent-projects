"""Bare ``node`` Click group definition.

Lives in its own module so each subcommand file under ``cli/node/``
can ``from tripwire.cli.node._group import node_cmd`` without
pulling in (and circularly importing) the subcommand modules registered
in ``cli/node/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="node")
def node_cmd() -> None:
    """Concept node operations: check freshness, inspect refs, render graphs."""
