"""``tripwire workspace pull`` — refresh workspace-origin nodes."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.workspace._group import workspace_cmd
from tripwire.cli.workspace._helpers import (
    _find_workspace_entry_for_project,
    _git_head,
    _git_show_node,
    _load_workspace_node,
    _resolve_workspace,
)

# Exit codes for sync operations:
# 0  — clean
# 1  — general error (project not linked, node not found, etc.)
# 10 — merges pending (pull produced briefs the agent must resolve)
# 11 — upstream divergence (push rejected; pull first)
EXIT_PULL_MERGES_PENDING = 10


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
        "\nRun /pm-project-sync (or `tripwire workspace merge-resolve <id>` per "
        "brief) to proceed."
    )
    raise click.exceptions.Exit(EXIT_PULL_MERGES_PENDING)
