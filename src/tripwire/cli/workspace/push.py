"""``tripwire workspace push`` — send local node changes upstream."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.cli.workspace._helpers import (
    _find_workspace_entry_for_project,
    _git_show_node,
    _load_workspace_node,
    _resolve_workspace,
)
from tripwire.core.store import load_project as load_project_config

# Exit codes for sync operations:
# 0  — clean
# 1  — general error (project not linked, node not found, etc.)
# 10 — merges pending (pull produced briefs the agent must resolve)
# 11 — upstream divergence (push rejected; pull first)
EXIT_PUSH_UPSTREAM_DIVERGED = 11


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
            "\nRun `tripwire workspace pull` first to merge upstream changes, then push."
        )
        raise click.exceptions.Exit(EXIT_PUSH_UPSTREAM_DIVERGED)

    if collisions:
        click.echo("Cannot push — workspace already has these ids:")
        for n in collisions:
            click.echo(f"  - {n}")
        click.echo(
            "\nRename your local node, or pull + fork if you're intentionally overriding."
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
        # StrEnum members → their string value, anything else that
        # doesn't round-trip through yaml.safe_dump gets coerced.
        from enum import Enum as _Enum
        from uuid import UUID as _UUID

        clean: dict[str, object] = {}
        for k, v in canonical.items():
            if hasattr(v, "isoformat"):
                clean[k] = v.isoformat()
            elif isinstance(v, _UUID):
                clean[k] = str(v)
            elif isinstance(v, _Enum):
                # NodeStatus and friends — write the string value so
                # the canonical workspace YAML stays loader-stable.
                clean[k] = v.value
            else:
                clean[k] = v
        dest.write_text(serialize_frontmatter_body(clean, body), encoding="utf-8")

    subprocess.run(["git", "add", "nodes/"], cwd=ws_dir, check=True)
    cfg = load_project_config(proj)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=tripwire",
            "-c",
            "user.email=tripwire@seido.dev",
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
