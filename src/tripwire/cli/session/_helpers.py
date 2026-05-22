"""Shared helpers for ``cli.session.*`` subcommand modules.

Leading underscore = private to this directory. Members used by exactly
one subcommand stay in that subcommand's file; helpers reach this module
the second they have ≥2 callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import click
from rich.console import Console

from tripwire.cli._utils import require_project as _require_project
from tripwire.core.session_store import load_session
from tripwire.models.session import AgentSession

console = Console()


def _resolve_and_load_session(
    project_dir: Path, session_id: str
) -> tuple[Path, AgentSession]:
    """Resolve *project_dir* and load *session_id*.

    Shared prelude for every ``tripwire session <verb> <session_id>``
    subcommand: expand-and-resolve the project path, assert the directory
    is a tripwire project, then load the session. Maps a missing
    session.yaml to ``click.ClickException`` so the CLI exits 1 with a
    readable message instead of a Python traceback.

    Commands that follow a different shape — ``session show`` and
    ``session check`` surface the underlying ``FileNotFoundError`` text,
    ``session abandon``/``reopen``/``cost`` wrap a different helper that
    raises ``FileNotFoundError`` — keep their own prelude.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    try:
        return resolved, load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"session {session_id!r} not found") from exc


@dataclass
class SessionSummary:
    id: str
    name: str
    agent: str
    status: str
    issue_count: int
    repo_count: int
    cost_usd: float = 0.0
    over_budget: bool = False


def _resolve_clone_path(project_dir: Path, repo_slug: str) -> Path | None:
    """Look up the local clone path for a repo from project.yaml."""
    from tripwire.core.store import load_project

    try:
        project = load_project(project_dir)
    except Exception:
        return None
    if not project.repos or not isinstance(project.repos, dict):
        return None
    repo_cfg = project.repos.get(repo_slug)
    if repo_cfg is None:
        return None
    local = getattr(repo_cfg, "local", None)
    if local is None:
        return None
    p = Path(local).expanduser()
    return p if p.exists() else None
