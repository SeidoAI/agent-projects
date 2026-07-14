"""``tripwire workspace status`` — sync state (workspace-side or project-side)."""

from __future__ import annotations

import json
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.core.store import load_project as load_project_config
from tripwire.core.workspace_store import load_workspace, workspace_exists


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
        click.echo(json.dumps({"workspace": ws.slug, "projects": rows}, indent=2))
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

    from tripwire.core.node_store import list_nodes

    nodes = list_nodes(proj_dir)
    workspace_origin = [n for n in nodes if n.origin == "workspace"]
    promotion_candidates = [
        n for n in nodes if n.origin == "local" and n.scope == "workspace"
    ]
    forks = [n for n in nodes if n.origin == "workspace" and n.scope == "local"]

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
