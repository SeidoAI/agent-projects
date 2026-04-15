"""`keel workspace` command group (v0.6b).

Subcommands:
- init                         — bootstrap a new workspace
- link <path>                  — register current project with a workspace
- unlink [--force]             — remove the project's workspace link
- list                         — enumerate registered projects
- status                       — sync state (workspace-side or project-side)
- prune [--force]              — remove orphan project entries
- copy <node-id>...            — import workspace nodes into project
- pull [--nodes] [--dry-run]   — refresh workspace-origin nodes
- push [--nodes] [--dry-run]   — send local node changes up
- fork <node-id>               — detach a workspace-origin node from sync
- promote <node-id>            — flip local node scope=workspace + push
- merge-resolve <node-id>      — finalize an agent-resolved merge
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import click

from keel import __version__ as KEEL_VERSION
from keel.cli._utils import require_project as _require_project
from keel.core.paths import workspace_nodes_dir
from keel.core.store import load_project as load_project_config
from keel.core.workspace_store import (
    add_project,
    load_workspace,
    remove_project,
    save_workspace,
    workspace_exists,
)
from keel.models.workspace import Workspace, WorkspaceProjectEntry


@click.group(name="workspace")
def workspace_cmd() -> None:
    """Workspace operations: init, link, sync, copy, pull/push/merge-resolve."""


# ============================================================================
# init
# ============================================================================


@workspace_cmd.command("init")
@click.option("--name", required=True, help="Human-readable workspace name.")
@click.option("--slug", required=True, help="Short alias (e.g. 'seido').")
@click.option("--description", default="", help="One-liner describing the workspace.")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_init_cmd(
    name: str, slug: str, description: str, workspace_dir: Path
) -> None:
    """Bootstrap a new workspace at WORKSPACE_DIR.

    Creates workspace.yaml, an empty nodes/ directory, and runs `git init`
    if the directory isn't already a git repo.
    """
    resolved = workspace_dir.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    if workspace_exists(resolved):
        raise click.ClickException(
            f"workspace already exists at {resolved} (workspace.yaml present)"
        )

    now = datetime.now(tz=timezone.utc)
    ws = Workspace(
        uuid=uuid4(),
        name=name,
        slug=slug,
        description=description,
        schema_version=1,
        keel_version=KEEL_VERSION,
        created_at=now,
        updated_at=now,
    )
    save_workspace(resolved, ws)
    workspace_nodes_dir(resolved).mkdir(parents=True, exist_ok=True)

    if not (resolved / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=resolved, check=True)

    click.echo(f"✓ Workspace '{name}' initialized at {resolved}")
    click.echo("  Next: from a project, `keel workspace link <path-to-workspace>`")


# ============================================================================
# link / unlink
# ============================================================================


@workspace_cmd.command("link")
@click.argument(
    "workspace_path",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--slug", required=True, help="Workspace-local alias for this project."
)
def workspace_link_cmd(
    workspace_path: Path, project_dir: Path, slug: str
) -> None:
    """Register the current project with a workspace (bidirectional)."""
    proj_resolved = project_dir.expanduser().resolve()
    ws_resolved = workspace_path.expanduser().resolve()
    _require_project(proj_resolved)

    if not workspace_exists(ws_resolved):
        raise click.ClickException(f"no workspace.yaml at {ws_resolved}")

    cfg = load_project_config(proj_resolved)
    if cfg.workspace is not None:
        raise click.ClickException(
            f"project is already linked to workspace at "
            f"{cfg.workspace.path}; run `keel workspace unlink` first"
        )

    # Write relative paths from each side.
    try:
        pointer_path = os.path.relpath(ws_resolved, proj_resolved)
    except ValueError:
        pointer_path = str(ws_resolved)
    try:
        ws_relative_back = os.path.relpath(proj_resolved, ws_resolved)
    except ValueError:
        ws_relative_back = str(proj_resolved)

    # Project-side: write workspace pointer.
    from keel.core.store import save_project
    from keel.models.project import ProjectWorkspacePointer

    cfg_new = cfg.model_copy(
        update={"workspace": ProjectWorkspacePointer(path=pointer_path)}
    )
    save_project(proj_resolved, cfg_new)

    # Workspace-side: register project entry.
    add_project(
        ws_resolved,
        WorkspaceProjectEntry(
            slug=slug, name=cfg.name, path=ws_relative_back
        ),
    )

    ws = load_workspace(ws_resolved)
    click.echo(f"✓ Linked {cfg.name} ↔ workspace {ws.slug}")
    click.echo(f"  project.yaml.workspace.path: {pointer_path}")
    click.echo(f"  workspace.yaml.projects[{slug}].path: {ws_relative_back}")


@workspace_cmd.command("unlink")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Remove the project-side pointer even if the workspace is missing.",
)
def workspace_unlink_cmd(project_dir: Path, force: bool) -> None:
    """Unlink this project from its workspace."""
    proj = project_dir.expanduser().resolve()
    _require_project(proj)

    from keel.core.store import save_project

    cfg = load_project_config(proj)
    if cfg.workspace is None:
        raise click.ClickException("project is not linked to any workspace")

    ws_resolved = (proj / cfg.workspace.path).resolve()

    if workspace_exists(ws_resolved):
        ws = load_workspace(ws_resolved)
        for p in list(ws.projects):
            if (ws_resolved / p.path).resolve() == proj:
                try:
                    remove_project(ws_resolved, slug=p.slug)
                except ValueError:
                    pass
    elif not force:
        raise click.ClickException(
            f"workspace at {ws_resolved} not found; re-run with --force "
            "to remove the project-side pointer only"
        )

    cfg_new = cfg.model_copy(update={"workspace": None})
    save_project(proj, cfg_new)
    click.echo("✓ Unlinked from workspace.")


# ============================================================================
# list / status / prune
# ============================================================================


@dataclass
class ProjectListRow:
    slug: str
    name: str
    path: str
    path_exists: bool
    last_pulled_sha: str | None
    last_pulled_at: str | None


@workspace_cmd.command("list")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def workspace_list_cmd(workspace_dir: Path, output_format: str) -> None:
    """List registered projects with sync state."""
    resolved = workspace_dir.expanduser().resolve()
    if not workspace_exists(resolved):
        raise click.ClickException(f"no workspace.yaml at {resolved}")
    ws = load_workspace(resolved)

    rows = []
    for p in ws.projects:
        path_exists = (resolved / p.path).resolve().exists()
        rows.append(
            ProjectListRow(
                slug=p.slug,
                name=p.name,
                path=p.path,
                path_exists=path_exists,
                last_pulled_sha=p.last_pulled_sha,
                last_pulled_at=(
                    p.last_pulled_at.isoformat() if p.last_pulled_at else None
                ),
            )
        )

    if output_format == "json":
        click.echo(json.dumps([asdict(r) for r in rows], indent=2))
        return

    if not rows:
        click.echo("no projects registered")
        return
    for r in rows:
        mark = "✓" if r.path_exists else "✗"
        status = "" if r.path_exists else "  (path not found — orphan)"
        click.echo(f"  {mark} {r.slug:12s} {r.name:20s} {r.path}{status}")
    orphans = sum(1 for r in rows if not r.path_exists)
    if orphans:
        click.echo(f"\n{orphans} orphan — run `keel workspace prune --force`")


@workspace_cmd.command("status")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def workspace_status_cmd(
    workspace_dir: Path | None,
    project_dir: Path | None,
    output_format: str,
) -> None:
    """Show sync state.

    From --workspace-dir: cross-project summary.
    From --project-dir: per-node inventory (counts of workspace-origin,
    promotion-candidate, fork).
    If neither flag is given, tries cwd (workspace first, then project).
    """
    resolved_ws = workspace_dir.expanduser().resolve() if workspace_dir else None
    resolved_proj = project_dir.expanduser().resolve() if project_dir else None

    if resolved_ws is None and resolved_proj is None:
        cwd = Path(".").resolve()
        if workspace_exists(cwd):
            resolved_ws = cwd
        else:
            resolved_proj = cwd
            _require_project(resolved_proj)

    if resolved_ws is not None:
        _status_workspace(resolved_ws, output_format)
    elif resolved_proj is not None:
        _status_project(resolved_proj, output_format)


def _status_workspace(ws_dir: Path, output_format: str) -> None:
    ws = load_workspace(ws_dir)
    rows = [
        {
            "slug": p.slug,
            "name": p.name,
            "last_pulled_at": (
                p.last_pulled_at.isoformat() if p.last_pulled_at else None
            ),
            "last_pushed_at": (
                p.last_pushed_at.isoformat() if p.last_pushed_at else None
            ),
        }
        for p in ws.projects
    ]
    if output_format == "json":
        click.echo(
            json.dumps({"workspace": ws.slug, "projects": rows}, indent=2)
        )
        return
    click.echo(f"Workspace: {ws.name} ({ws.slug})")
    for r in rows:
        click.echo(
            f"  {r['slug']:12s} pulled {r['last_pulled_at'] or '—'}, "
            f"pushed {r['last_pushed_at'] or '—'}"
        )


def _status_project(proj_dir: Path, output_format: str) -> None:
    cfg = load_project_config(proj_dir)
    if cfg.workspace is None:
        click.echo("project is not linked to a workspace")
        return

    ws_resolved = (proj_dir / cfg.workspace.path).resolve()

    from keel.core.node_store import list_nodes

    nodes = list_nodes(proj_dir)
    workspace_origin = [n for n in nodes if n.origin == "workspace"]
    promotion_candidates = [
        n for n in nodes if n.origin == "local" and n.scope == "workspace"
    ]
    forks = [
        n for n in nodes if n.origin == "workspace" and n.scope == "local"
    ]

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "workspace_path": str(ws_resolved),
                    "workspace_origin_count": len(workspace_origin),
                    "promotion_candidate_count": len(promotion_candidates),
                    "fork_count": len(forks),
                },
                indent=2,
            )
        )
        return

    click.echo(f"Project linked to: {ws_resolved}")
    click.echo(f"  workspace-origin nodes: {len(workspace_origin)}")
    click.echo(f"  promotion candidates:   {len(promotion_candidates)}")
    click.echo(f"  forks:                  {len(forks)}")


@workspace_cmd.command("prune")
@click.option(
    "--workspace-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Actually remove orphan entries. Default is dry-run.",
)
def workspace_prune_cmd(workspace_dir: Path, force: bool) -> None:
    """Remove orphan project entries (path no longer exists)."""
    resolved = workspace_dir.expanduser().resolve()
    if not workspace_exists(resolved):
        raise click.ClickException(f"no workspace.yaml at {resolved}")
    ws = load_workspace(resolved)
    orphans = [
        p for p in ws.projects if not (resolved / p.path).resolve().exists()
    ]
    if not orphans:
        click.echo("no orphans")
        return
    if not force:
        click.echo("would remove:")
        for p in orphans:
            click.echo(f"  {p.slug} ({p.path})")
        click.echo("re-run with --force to actually remove")
        return
    for p in orphans:
        remove_project(resolved, slug=p.slug)
    click.echo(f"removed {len(orphans)} orphan(s)")
