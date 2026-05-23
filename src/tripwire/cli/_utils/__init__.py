"""Shared CLI helpers + true cross-entity user-facing utility commands.

This package hosts both shared helpers (e.g. ``require_project``) and
small user-facing utility commands like ``tripwire uuid`` and
``tripwire completion`` that don't belong to any single entity. Each
command module registers itself as a top-level Click command via
``cli.add_command`` in ``cli/main.py`` — the ``_utils/`` prefix is
internal organization, not part of the user-facing CLI surface.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.core.store import ProjectNotFoundError, load_project


def require_project(project_dir: Path) -> None:
    """Confirm the directory is a tripwire project, or raise a ClickException.

    Called at the top of read-only commands that need `project.yaml` to
    exist before they do anything.
    """
    try:
        load_project(project_dir)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
