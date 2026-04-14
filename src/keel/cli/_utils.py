"""Shared CLI helpers.

Small utilities used by multiple CLI command modules. Prefer importing
from here over re-implementing the same helper in each command.
"""

from __future__ import annotations

from pathlib import Path

import click

from keel.core.store import ProjectNotFoundError, load_project


def require_project(project_dir: Path) -> None:
    """Confirm the directory is a keel project, or raise a ClickException.

    Called at the top of read-only commands that need `project.yaml` to
    exist before they do anything.
    """
    try:
        load_project(project_dir)
    except ProjectNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
