"""Workspace linking + node-copy for ``tripwire init --workspace`` (v0.6b).

Registers the freshly-init'd project under the named workspace and
optionally copies a comma-separated list of canonical nodes from the
workspace into the local project.

The CLI wrapper at ``cli/init.py`` calls :func:`link_to_workspace`;
on failure it raises :class:`ValueError` (the CLI converts to InitError).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console

from tripwire.core.init_github import git_head_short
from tripwire.core.node_store import node_exists, save_node
from tripwire.core.parser import parse_frontmatter_body
from tripwire.core.paths import workspace_node_path
from tripwire.core.store import load_project, save_project
from tripwire.core.workspace_store import add_project as _ws_add_project
from tripwire.core.workspace_store import workspace_exists as _ws_exists
from tripwire.models.node import ConceptNode
from tripwire.models.project import ProjectWorkspacePointer
from tripwire.models.workspace import WorkspaceProjectEntry


def link_to_workspace(
    *,
    target_dir: Path,
    workspace_path: Path,
    key_prefix: str,
    project_name: str,
    copy_nodes: str | None,
    console: Console | None = None,
) -> None:
    """Link the newly-init'd project to a workspace + optionally copy nodes.

    Uses the internal Python API directly (no subprocess / no ``uv``
    dependency) so this works in any install environment.

    Raises:
        ValueError: workspace.yaml absent, slug-collision in the
            workspace registry, or any other linking failure that
            should abort init.
    """
    if console is None:
        console = Console()

    slug = key_prefix.lower()

    if not _ws_exists(workspace_path):
        raise ValueError(f"No workspace.yaml at {workspace_path}")

    # Compute relative paths from each side.
    try:
        pointer_path = os.path.relpath(workspace_path, target_dir)
    except ValueError:
        pointer_path = str(workspace_path)
    try:
        ws_relative_back = os.path.relpath(target_dir, workspace_path)
    except ValueError:
        ws_relative_back = str(target_dir)

    # Write workspace-side FIRST so that if it fails (e.g. duplicate
    # slug) the project-side pointer hasn't been written yet — avoiding
    # a one-sided link.
    try:
        _ws_add_project(
            workspace_path,
            WorkspaceProjectEntry(
                slug=slug,
                name=project_name,
                path=ws_relative_back,
            ),
        )
    except ValueError as exc:
        raise ValueError(f"Failed to register in workspace: {exc}") from exc

    cfg = load_project(target_dir)
    cfg_new = cfg.model_copy(
        update={"workspace": ProjectWorkspacePointer(path=pointer_path)}
    )
    save_project(target_dir, cfg_new)

    console.print(
        f"[dim]✓ Linked {project_name} to workspace at {workspace_path}[/dim]"
    )

    if copy_nodes:
        node_ids = [nid.strip() for nid in copy_nodes.split(",") if nid.strip()]
        head_sha = git_head_short(workspace_path)
        copied = 0
        for nid in node_ids:
            if node_exists(target_dir, nid):
                console.print(
                    f"[yellow]⚠ {nid}: already exists locally, skipped[/yellow]"
                )
                continue
            try:
                ws_node_path = workspace_node_path(workspace_path, nid)
                if not ws_node_path.is_file():
                    console.print(f"[yellow]⚠ {nid}: not found in workspace[/yellow]")
                    continue
                text = ws_node_path.read_text(encoding="utf-8")
                fm, _body = parse_frontmatter_body(text)
                canonical = ConceptNode.model_validate(fm)
                local_copy = canonical.model_copy(
                    update={
                        "origin": "workspace",
                        "scope": "workspace",
                        "workspace_sha": head_sha,
                        "workspace_pulled_at": datetime.now(tz=timezone.utc),
                    }
                )
                save_node(target_dir, local_copy, update_cache=False)
                copied += 1
            except Exception as exc:
                console.print(f"[yellow]⚠ {nid}: copy failed: {exc}[/yellow]")
        if copied:
            console.print(f"[dim]✓ Copied {copied} node(s) from workspace[/dim]")
