"""Shared helpers for ``cli.workspace.*`` subcommand modules.

Leading underscore = private to this directory. Members used by exactly
one subcommand stay in that subcommand's file; helpers reach this module
the second they have ≥2 callers.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from tripwire.core.store import load_project as load_project_config
from tripwire.core.workspace_store import load_workspace, workspace_exists


def _git_head(repo_dir: Path) -> str:
    """Return the short SHA of HEAD in the given git repo."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_show_node(ws_dir: Path, sha: str, node_id: str) -> dict:
    """Read a node's frontmatter from a specific workspace commit.

    Raises FileNotFoundError if the file doesn't exist at that sha.
    """
    import yaml as _yaml

    result = subprocess.run(
        ["git", "show", f"{sha}:nodes/{node_id}.yaml"],
        cwd=ws_dir,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FileNotFoundError(f"node {node_id} at sha {sha} not in workspace history")
    text = result.stdout
    parts = text.split("---", 2)
    if len(parts) < 2:
        raise ValueError(f"malformed frontmatter for {node_id} at {sha}")
    return _yaml.safe_load(parts[1])


def _load_workspace_node(ws_dir: Path, node_id: str):
    """Load a node from <ws_dir>/nodes/<node_id>.yaml (working tree)."""
    from tripwire.core.parser import ParseError, parse_frontmatter_body
    from tripwire.core.paths import workspace_node_path
    from tripwire.models.node import ConceptNode

    path = workspace_node_path(ws_dir, node_id)
    if not path.is_file():
        raise FileNotFoundError(f"node {node_id} not in workspace")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, _body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return ConceptNode.model_validate(frontmatter)


def _resolve_workspace(proj_dir: Path) -> Path:
    """Resolve the workspace directory from a project's link pointer."""
    cfg = load_project_config(proj_dir)
    if cfg.workspace is None:
        raise click.ClickException("project is not linked to a workspace")
    ws_resolved = (proj_dir / cfg.workspace.path).resolve()
    if not workspace_exists(ws_resolved):
        raise click.ClickException(
            f"linked workspace at {ws_resolved} has no workspace.yaml"
        )
    return ws_resolved


def _find_workspace_entry_for_project(ws_dir: Path, proj_dir: Path):
    """Return the WorkspaceProjectEntry that points at proj_dir, or None."""
    ws = load_workspace(ws_dir)
    for entry in ws.projects:
        if (ws_dir / entry.path).resolve() == proj_dir:
            return entry
    return None
