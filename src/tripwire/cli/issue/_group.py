"""Bare ``issue`` Click group definition.

Lives in its own module so each subcommand file under ``cli/issue/`` can
``from tripwire.cli.issue._group import issue_cmd`` without pulling in
(and circularly importing) the subcommand modules registered in
``cli/issue/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="issue")
def issue_cmd() -> None:
    """Per-issue operations (artifact + insights subgroups)."""
