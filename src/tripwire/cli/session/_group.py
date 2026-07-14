"""Bare ``session`` Click group definition.

Lives in its own module so each subcommand file under ``cli/session/``
can ``from tripwire.cli.session._group import session_cmd`` without
pulling in (and circularly importing) the subcommand modules registered
in ``cli/session/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="session")
def session_cmd() -> None:
    """Session operations (read-only in v0)."""
