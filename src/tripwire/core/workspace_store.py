"""Read/write workspace.yaml.

Follows the same frontmatter-YAML pattern as other tripwire stores.
Registry-mutation functions acquire a lock on the workspace's lock file
and update atomically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.locks import project_lock
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.core.paths import workspace_yaml_path
from tripwire.models.workspace import Workspace, WorkspaceProjectEntry


def workspace_exists(workspace_dir: Path) -> bool:
    return workspace_yaml_path(workspace_dir).is_file()


def load_workspace(workspace_dir: Path) -> Workspace:
    path = workspace_yaml_path(workspace_dir)
    if not path.exists():
        raise FileNotFoundError(f"workspace.yaml not found at {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, _body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return Workspace.model_validate(frontmatter)


def save_workspace(workspace_dir: Path, workspace: Workspace) -> None:
    path = workspace_yaml_path(workspace_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    workspace = workspace.model_copy(
        update={"updated_at": datetime.now(tz=timezone.utc)}
    )
    data = workspace.model_dump(mode="json", exclude_none=True)
    text = serialize_frontmatter_body(data, "")
    path.write_text(text, encoding="utf-8")


def add_project(workspace_dir: Path, entry: WorkspaceProjectEntry) -> None:
    """Register a new project. Raises ValueError on duplicate slug."""
    with project_lock(workspace_dir):
        ws = load_workspace(workspace_dir)
        if any(p.slug == entry.slug for p in ws.projects):
            raise ValueError(f"project slug '{entry.slug}' already registered")
        ws = ws.model_copy(update={"projects": [*ws.projects, entry]})
        save_workspace(workspace_dir, ws)


def remove_project(workspace_dir: Path, *, slug: str) -> None:
    """Remove a project from the workspace registry. Raises ValueError if missing."""
    with project_lock(workspace_dir):
        ws = load_workspace(workspace_dir)
        kept = [p for p in ws.projects if p.slug != slug]
        if len(kept) == len(ws.projects):
            raise ValueError(f"project slug '{slug}' not found in workspace")
        ws = ws.model_copy(update={"projects": kept})
        save_workspace(workspace_dir, ws)


def update_project_pull_state(
    workspace_dir: Path, *, slug: str, sha: str, at: datetime
) -> None:
    with project_lock(workspace_dir):
        ws = load_workspace(workspace_dir)
        updated = [
            p.model_copy(update={"last_pulled_sha": sha, "last_pulled_at": at})
            if p.slug == slug
            else p
            for p in ws.projects
        ]
        ws = ws.model_copy(update={"projects": updated})
        save_workspace(workspace_dir, ws)


def update_project_push_state(
    workspace_dir: Path, *, slug: str, sha: str, at: datetime
) -> None:
    with project_lock(workspace_dir):
        ws = load_workspace(workspace_dir)
        updated = [
            p.model_copy(update={"last_pushed_sha": sha, "last_pushed_at": at})
            if p.slug == slug
            else p
            for p in ws.projects
        ]
        ws = ws.model_copy(update={"projects": updated})
        save_workspace(workspace_dir, ws)
