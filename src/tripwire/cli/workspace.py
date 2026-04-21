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

from tripwire import __version__ as TRIPWIRE_VERSION
from tripwire.cli._utils import require_project as _require_project
from tripwire.core.paths import workspace_nodes_dir
from tripwire.core.store import load_project as load_project_config
from tripwire.core.workspace_store import (
    add_project,
    load_workspace,
    remove_project,
    save_workspace,
    workspace_exists,
)
from tripwire.models.workspace import Workspace, WorkspaceProjectEntry


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
        tripwire_version=TRIPWIRE_VERSION,
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
@click.option("--slug", required=True, help="Workspace-local alias for this project.")
def workspace_link_cmd(workspace_path: Path, project_dir: Path, slug: str) -> None:
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

    from tripwire.core.store import save_project
    from tripwire.models.project import ProjectWorkspacePointer

    # Write workspace-side FIRST. If it fails (e.g. duplicate slug,
    # lock timeout, write error) the project-side pointer hasn't been
    # touched yet — no one-sided link to clean up.
    add_project(
        ws_resolved,
        WorkspaceProjectEntry(slug=slug, name=cfg.name, path=ws_relative_back),
    )

    # Project-side: write workspace pointer. If THIS fails (unlikely —
    # it's a local file write), we have a workspace entry without a
    # project pointer, which is the safer half-state: `workspace list`
    # will show it and `workspace prune` can clean it up.
    cfg_new = cfg.model_copy(
        update={"workspace": ProjectWorkspacePointer(path=pointer_path)}
    )
    save_project(proj_resolved, cfg_new)

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

    from tripwire.core.store import save_project

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
    orphans = [p for p in ws.projects if not (resolved / p.path).resolve().exists()]
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


# ============================================================================
# Git helpers (shared across copy/pull/push/merge-resolve)
# ============================================================================


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


# ============================================================================
# copy
# ============================================================================


@workspace_cmd.command("copy")
@click.argument("node_ids", nargs=-1, required=True)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_copy_cmd(node_ids: tuple[str, ...], project_dir: Path) -> None:
    """Import workspace nodes into this project for the first time.

    Each node is stamped with origin=workspace, scope=workspace, and
    workspace_sha = current workspace HEAD. Refuses when the node id
    already exists locally — use `pull` (to refresh) or `fork` (to
    detach) instead.
    """
    from tripwire.core.node_store import node_exists, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    head_sha = _git_head(ws_dir)
    copied: list[str] = []
    skipped: list[tuple[str, str]] = []

    for node_id in node_ids:
        if node_exists(proj, node_id):
            skipped.append((node_id, "already exists locally"))
            continue
        try:
            canonical = _load_workspace_node(ws_dir, node_id)
        except FileNotFoundError:
            skipped.append((node_id, "not found in workspace"))
            continue

        local_copy = canonical.model_copy(
            update={
                "origin": "workspace",
                "scope": "workspace",
                "workspace_sha": head_sha,
                "workspace_pulled_at": datetime.now(tz=timezone.utc),
            }
        )
        save_node(proj, local_copy, update_cache=False)
        copied.append(node_id)

    for node_id in copied:
        click.echo(f"✓ {node_id}")
    for node_id, reason in skipped:
        click.echo(f"✗ {node_id}: {reason}")
    click.echo(
        f"\n{len(copied)} of {len(node_ids)} node(s) copied; workspace_sha={head_sha}."
    )
    if skipped and not copied:
        raise click.exceptions.Exit(1)


# ============================================================================
# pull
# ============================================================================


# Exit codes for sync operations:
# 0  — clean
# 1  — general error (project not linked, node not found, etc.)
# 10 — merges pending (pull produced briefs the agent must resolve)
# 11 — upstream divergence (push rejected; pull first)
EXIT_PULL_MERGES_PENDING = 10
EXIT_PUSH_UPSTREAM_DIVERGED = 11


@workspace_cmd.command("pull")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--nodes",
    default=None,
    help="Comma-separated node ids (default: all workspace-origin nodes).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Report without applying.")
def workspace_pull_cmd(project_dir: Path, nodes: str | None, dry_run: bool) -> None:
    """Pull workspace node updates into this project.

    Fast-forwards and non-overlapping field changes are applied
    automatically. Conflicts produce merge briefs (v0.6b T19) and the
    command exits 10 signalling "merges pending".
    """
    from tripwire.core.node_store import list_nodes, save_node
    from tripwire.core.workspace_store import update_project_pull_state
    from tripwire.core.workspace_sync import MergeStatus, merge_nodes
    from tripwire.models.node import ConceptNode

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    target_ids = set(nodes.split(",")) if nodes else None
    workspace_head = _git_head(ws_dir)

    # Only workspace-origin AND scope=workspace nodes participate.
    # Forked nodes (scope=local) are deliberately skipped.
    candidates = [
        n
        for n in list_nodes(proj)
        if n.origin == "workspace" and n.scope == "workspace"
    ]
    if target_ids is not None:
        candidates = [n for n in candidates if n.id in target_ids]

    auto_merged: list[str] = []
    conflicts: list[tuple[str, object]] = []  # (node_id, MergeResult)
    skipped: list[tuple[str, str]] = []
    fast_forwards: list[str] = []

    # Used later for brief generation on conflict.
    conflict_context: dict[str, tuple[dict, dict, dict]] = {}

    for node in candidates:
        ours_dict = node.model_dump(mode="python")
        try:
            theirs_node = _load_workspace_node(ws_dir, node.id)
        except FileNotFoundError:
            skipped.append((node.id, "deleted upstream"))
            continue
        theirs_dict = theirs_node.model_dump(mode="python")
        try:
            base_dict = _git_show_node(ws_dir, node.workspace_sha, node.id)
        except FileNotFoundError:
            skipped.append(
                (node.id, f"workspace_sha {node.workspace_sha} not in history")
            )
            continue

        result = merge_nodes(base=base_dict, ours=ours_dict, theirs=theirs_dict)

        if result.status is MergeStatus.NO_CHANGES:
            continue
        if result.status is MergeStatus.NO_UPSTREAM_CHANGES:
            continue

        if result.status is MergeStatus.CONFLICT:
            conflicts.append((node.id, result))
            conflict_context[node.id] = (base_dict, ours_dict, theirs_dict)
            continue

        # FAST_FORWARD or AUTO_MERGED — apply.
        if dry_run:
            (
                fast_forwards
                if result.status is MergeStatus.FAST_FORWARD
                else auto_merged
            ).append(node.id)
            continue

        merged_bookkept = dict(result.merged)  # type: ignore[arg-type]
        merged_bookkept.update(
            {
                "origin": "workspace",
                "scope": "workspace",
                "workspace_sha": workspace_head,
                "workspace_pulled_at": datetime.now(tz=timezone.utc),
            }
        )
        updated = ConceptNode.model_validate(merged_bookkept)
        save_node(proj, updated, update_cache=False)
        (
            fast_forwards if result.status is MergeStatus.FAST_FORWARD else auto_merged
        ).append(node.id)

    # Report.
    for n in fast_forwards:
        click.echo(f"✓ {n}: fast-forward")
    for n in auto_merged:
        click.echo(f"✓ {n}: auto-merged")
    for n, reason in skipped:
        click.echo(f"⚠ {n}: {reason}")

    if not conflicts:
        if not dry_run and (fast_forwards or auto_merged):
            entry = _find_workspace_entry_for_project(ws_dir, proj)
            if entry is not None:
                update_project_pull_state(
                    ws_dir,
                    slug=entry.slug,
                    sha=workspace_head,
                    at=datetime.now(tz=timezone.utc),
                )
        if fast_forwards or auto_merged:
            click.echo(
                f"\n{len(fast_forwards) + len(auto_merged)} node(s) pulled; "
                f"workspace_sha now {workspace_head}."
            )
        else:
            click.echo("\nAlready up to date.")
        return

    # Conflicts present — generate structured briefs for each and write
    # a draft merge (auto-merged fields applied; conflicting fields left
    # as ours as a starting point for the agent).
    from tripwire.core.merge_brief import MergeType, build_merge_brief, save_merge_brief

    for node_id, result in conflicts:
        base_dict, ours_dict, theirs_dict = conflict_context[node_id]

        if dry_run:
            # Dry-run: report the conflict but write nothing to disk.
            continue

        brief = build_merge_brief(
            node_id=node_id,
            merge_type=MergeType.PULL,
            base_sha=ours_dict.get("workspace_sha") or "",
            base=base_dict,
            ours=ours_dict,
            theirs=theirs_dict,
            auto_merged_fields=result.auto_merged_fields,  # type: ignore[attr-defined]
        )
        save_merge_brief(proj, brief)

        # Draft merge starting point: apply auto-merged fields, take ours
        # for conflicting fields, keep workspace_sha unchanged until the
        # agent runs merge-resolve.
        draft = dict(base_dict)
        for f in result.auto_merged_fields:  # type: ignore[attr-defined]
            if ours_dict.get(f) != base_dict.get(f):
                draft[f] = ours_dict[f]
            else:
                draft[f] = theirs_dict[f]
        for f in result.conflicting_fields:  # type: ignore[attr-defined]
            draft[f] = ours_dict[f]
        draft.update(
            {
                "origin": "workspace",
                "scope": "workspace",
                "workspace_sha": ours_dict["workspace_sha"],
                "workspace_pulled_at": datetime.now(tz=timezone.utc),
            }
        )
        save_node(proj, ConceptNode.model_validate(draft), update_cache=False)

    click.echo(f"\nNeeds agent resolution ({len(conflicts)}):")
    for node_id, _ in conflicts:
        click.echo(f"  → .tripwire/merge-briefs/{node_id}.yaml")
    click.echo(
        "\nRun /pm-project-sync (or `keel workspace merge-resolve <id>` per "
        "brief) to proceed."
    )
    raise click.exceptions.Exit(EXIT_PULL_MERGES_PENDING)


# ============================================================================
# push
# ============================================================================


@workspace_cmd.command("push")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--nodes",
    default=None,
    help="Comma-separated node ids (default: all with pending changes).",
)
@click.option("--dry-run", is_flag=True, default=False, help="Report without applying.")
def workspace_push_cmd(project_dir: Path, nodes: str | None, dry_run: bool) -> None:
    """Propose project node changes upstream to workspace.

    Two kinds of nodes participate:
    1. Modified workspace-origin (origin=workspace, scope=workspace)
    2. Promotion candidates (origin=local, scope=workspace)

    Upstream divergence (another agent pushed something since our last
    pull on the same node) causes push to refuse with exit 11.
    """

    from tripwire.core.node_store import list_nodes
    from tripwire.core.paths import workspace_node_path
    from tripwire.core.workspace_sync import MergeStatus, merge_nodes

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    target_ids = set(nodes.split(",")) if nodes else None

    pushes: list[tuple[str, str, dict]] = []  # (node_id, action, final_dict)
    diverged: list[str] = []
    collisions: list[str] = []

    for node in list_nodes(proj):
        if target_ids is not None and node.id not in target_ids:
            continue

        if node.origin == "workspace" and node.scope == "workspace":
            # Check for local modifications + upstream divergence.
            ours_dict = node.model_dump(mode="python")
            try:
                theirs_node = _load_workspace_node(ws_dir, node.id)
            except FileNotFoundError:
                # Deleted upstream — skip. (Handled by pull's deletion warning.)
                continue
            theirs_dict = theirs_node.model_dump(mode="python")
            try:
                base_dict = _git_show_node(ws_dir, node.workspace_sha, node.id)
            except FileNotFoundError:
                # Stale workspace_sha — treat as diverged, user must pull/fork.
                diverged.append(node.id)
                continue

            result = merge_nodes(base=base_dict, ours=ours_dict, theirs=theirs_dict)
            if result.status is MergeStatus.CONFLICT:
                diverged.append(node.id)
                continue
            if result.status is MergeStatus.NO_UPSTREAM_CHANGES:
                pushes.append((node.id, "fast-forward", ours_dict))
            elif result.status is MergeStatus.AUTO_MERGED:
                pushes.append((node.id, "auto-merged", result.merged))  # type: ignore[arg-type]
            # NO_CHANGES / FAST_FORWARD (ours==base): nothing to push.

        elif node.origin == "local" and node.scope == "workspace":
            # Promotion candidate: check for id collision in workspace.
            if workspace_node_path(ws_dir, node.id).exists():
                collisions.append(node.id)
                continue
            pushes.append((node.id, "promotion", node.model_dump(mode="python")))

    if diverged:
        click.echo("Cannot push — upstream has diverged since last pull for:")
        for n in diverged:
            click.echo(f"  - {n}")
        click.echo(
            "\nRun `keel workspace pull` first to merge upstream changes, then push."
        )
        raise click.exceptions.Exit(EXIT_PUSH_UPSTREAM_DIVERGED)

    if collisions:
        click.echo("Cannot push — workspace already has these ids:")
        for n in collisions:
            click.echo(f"  - {n}")
        click.echo(
            "\nRename your local node, or pull+fork if you're intentionally overriding."
        )
        raise click.exceptions.Exit(1)

    if not pushes:
        click.echo("nothing to push")
        return

    if dry_run:
        for node_id, action, _ in pushes:
            click.echo(f"would {action}: {node_id}")
        return

    # Acquire the workspace lock for the entire write-commit-bookkeep
    # sequence. Without this, concurrent pushes from different project
    # repos race on git's own index.lock and one or more may fail.
    from tripwire.core.locks import project_lock

    with project_lock(ws_dir):
        _apply_pushes(proj, ws_dir, pushes)


def _apply_pushes(
    proj: Path, ws_dir: Path, pushes: list[tuple[str, str, dict]]
) -> None:
    """Write node files to the workspace, commit, and update bookkeeping.

    Called while holding the workspace lock.
    """
    from tripwire.core.node_store import save_node
    from tripwire.core.parser import serialize_frontmatter_body
    from tripwire.core.paths import workspace_node_path
    from tripwire.models.node import ConceptNode

    # Write each push to the workspace working tree.
    for node_id, _action, final_dict in pushes:
        canonical = dict(final_dict)
        canonical["origin"] = "workspace"
        canonical["scope"] = "workspace"
        # Canonical nodes in the workspace repo don't carry project-side
        # bookkeeping.
        for field_to_strip in (
            "workspace_sha",
            "workspace_pulled_at",
        ):
            canonical.pop(field_to_strip, None)

        dest = workspace_node_path(ws_dir, node_id)
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Serialise via the shared parser's convention (frontmatter + body).
        body = canonical.pop("body", "")

        # Normalise for YAML: datetimes → iso strings, UUIDs → str,
        # anything else that doesn't round-trip through yaml.safe_dump
        # gets coerced via json-mode dump.
        from uuid import UUID as _UUID

        clean: dict[str, object] = {}
        for k, v in canonical.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, _UUID):
                clean[k] = str(v)
            else:
                clean[k] = v
        dest.write_text(serialize_frontmatter_body(clean, body), encoding="utf-8")

    subprocess.run(["git", "add", "nodes/"], cwd=ws_dir, check=True)
    cfg = load_project_config(proj)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=keel",
            "-c",
            "user.email=keel@seido.dev",
            "commit",
            "-q",
            "-m",
            f"push: {len(pushes)} node(s) from {cfg.name}",
        ],
        cwd=ws_dir,
        check=True,
    )
    new_sha = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ws_dir,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    # Update local bookkeeping on each pushed node.
    for _node_id, _action, final_dict in pushes:
        local = dict(final_dict)
        local.update(
            {
                "origin": "workspace",
                "scope": "workspace",
                "workspace_sha": new_sha,
                "workspace_pulled_at": datetime.now(tz=timezone.utc),
            }
        )
        save_node(proj, ConceptNode.model_validate(local), update_cache=False)

    # Update workspace.yaml's last_pushed_sha for this project.
    # We already hold the workspace lock via the enclosing context
    # manager — inline the mutation to avoid re-entering project_lock.
    from tripwire.core.workspace_store import load_workspace, save_workspace

    entry = _find_workspace_entry_for_project(ws_dir, proj)
    if entry is not None:
        ws = load_workspace(ws_dir)
        now = datetime.now(tz=timezone.utc)
        updated = [
            p.model_copy(update={"last_pushed_sha": new_sha, "last_pushed_at": now})
            if p.slug == entry.slug
            else p
            for p in ws.projects
        ]
        save_workspace(ws_dir, ws.model_copy(update={"projects": updated}))

    for node_id, action, _ in pushes:
        click.echo(f"✓ {node_id}: {action}")
    click.echo(f"\n{len(pushes)} node(s) pushed; workspace at {new_sha}.")


# ============================================================================
# fork
# ============================================================================


@workspace_cmd.command("fork")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_fork_cmd(node_id: str, project_dir: Path) -> None:
    """Detach a workspace-origin node from sync (scope workspace → local).

    The node keeps origin=workspace + workspace_sha for audit, but pull
    and push skip it. Useful when a project needs to specialize a node
    without tracking upstream changes.
    """
    from tripwire.core.node_store import load_node, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)

    try:
        node = load_node(proj, node_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"node '{node_id}' not found in project") from exc

    if node.origin != "workspace":
        raise click.ClickException(
            f"node '{node_id}' has origin=local — nothing to fork from"
        )
    if node.scope == "local":
        click.echo(
            f"node '{node_id}' is already forked (origin=workspace, scope=local)"
        )
        return

    forked = node.model_copy(update={"scope": "local"})
    save_node(proj, forked, update_cache=False)
    click.echo(
        f"✓ Forked {node_id}. origin={forked.origin} scope={forked.scope} "
        f"workspace_sha={forked.workspace_sha} (kept for audit)."
    )


# ============================================================================
# promote
# ============================================================================


@workspace_cmd.command("promote")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.pass_context
def workspace_promote_cmd(ctx: click.Context, node_id: str, project_dir: Path) -> None:
    """Promote a local node to workspace (scope local → workspace + push).

    Shortcut that flips ``scope`` and delegates to push. Refuses if the
    node is already workspace-origin (use pull/push directly) or if the
    workspace already has a node with the same id.
    """
    from tripwire.core.node_store import load_node, save_node
    from tripwire.core.paths import workspace_node_path

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    try:
        node = load_node(proj, node_id)
    except FileNotFoundError as exc:
        raise click.ClickException(f"node '{node_id}' not found in project") from exc

    if node.origin != "local":
        raise click.ClickException(
            f"node '{node_id}' is already origin=workspace; promote only "
            "applies to local-origin nodes. Use `keel workspace push` to "
            "send pending changes upstream."
        )

    if workspace_node_path(ws_dir, node_id).exists():
        raise click.ClickException(
            f"workspace already has a node with id '{node_id}'. Rename your "
            "local node, or pull + fork if you're intentionally overriding."
        )

    # Flip scope and delegate to push.
    promoted = node.model_copy(update={"scope": "workspace"})
    save_node(proj, promoted, update_cache=False)
    click.echo(f"marked {node_id} as scope=workspace; pushing...")
    ctx.invoke(
        workspace_push_cmd,
        project_dir=proj,
        nodes=node_id,
        dry_run=False,
    )


# ============================================================================
# merge-resolve
# ============================================================================


@workspace_cmd.command("merge-resolve")
@click.argument("node_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def workspace_merge_resolve_cmd(node_id: str, project_dir: Path) -> None:
    """Finalize an agent-resolved merge.

    Validates the resolved node against the schema, bumps its
    workspace_sha to the current workspace HEAD, and deletes the
    merge brief. If validation fails, the brief is preserved so the
    agent can fix the node and retry.
    """
    from tripwire.core.merge_brief import (
        delete_merge_brief,
        list_pending_briefs,
        load_merge_brief,
    )
    from tripwire.core.node_store import load_node, save_node

    proj = project_dir.expanduser().resolve()
    _require_project(proj)
    ws_dir = _resolve_workspace(proj)

    brief = load_merge_brief(proj, node_id)
    if brief is None:
        raise click.ClickException(
            f"no pending merge brief for '{node_id}' at "
            f".tripwire/merge-briefs/{node_id}.yaml"
        )

    try:
        node = load_node(proj, node_id)
    except Exception as exc:
        raise click.ClickException(
            f"node '{node_id}' failed to load after resolve: {exc}. "
            "Brief preserved — fix the node file and retry."
        ) from exc

    workspace_head = _git_head(ws_dir)
    resolved = node.model_copy(
        update={
            "origin": "workspace",
            "scope": "workspace",
            "workspace_sha": workspace_head,
            "workspace_pulled_at": datetime.now(tz=timezone.utc),
        }
    )
    save_node(proj, resolved, update_cache=False)
    delete_merge_brief(proj, node_id)

    click.echo(f"✓ {node_id}: resolved")
    click.echo(f"  workspace_sha → {workspace_head}")
    click.echo("  brief deleted")

    remaining = list_pending_briefs(proj)
    if remaining:
        click.echo(f"\n{len(remaining)} brief(s) still pending: {', '.join(remaining)}")
    else:
        click.echo("\nAll merges resolved. Pull complete.")
