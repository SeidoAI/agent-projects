"""Bare ``pr`` Click group definition.

Lives in its own module so each subcommand file under ``cli/pr/``
can ``from tripwire.cli.pr._group import pr_cmd`` without
pulling in (and circularly importing) the subcommand modules registered
in ``cli/pr/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="pr")
def pr_cmd() -> None:
    """PR-side operations: status queries, summaries, and the watch daemon."""
