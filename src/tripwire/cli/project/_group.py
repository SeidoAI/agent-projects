"""Bare ``project`` Click group definition.

Lives in its own module so each subcommand file under ``cli/project/``
can ``from tripwire.cli.project._group import project_cmd`` without
pulling in (and circularly importing) the subcommand modules registered
in ``cli/project/__init__.py``.
"""

from __future__ import annotations

import click


@click.group(name="project")
def project_cmd() -> None:
    """Project lifecycle operations: init, brief, readme."""
