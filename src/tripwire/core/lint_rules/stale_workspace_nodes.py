"""lint/stale_workspace_nodes — warn when workspace-origin nodes are
behind workspace HEAD.

Scoping + handoff stages. No-op when the project isn't linked or the
linked workspace isn't reachable.
"""

from __future__ import annotations

import subprocess

from tripwire.core.linter import LintFinding, register_rule
from tripwire.core.node_store import list_nodes
from tripwire.core.store import load_project


def _check(ctx):
    try:
        cfg = load_project(ctx.project_dir)
    except Exception:
        return
    if cfg.workspace is None:
        return
    ws_dir = (ctx.project_dir / cfg.workspace.path).resolve()
    if not (ws_dir / ".git").exists():
        return  # unreachable or orphan — other rules handle that

    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ws_dir,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        return

    for n in list_nodes(ctx.project_dir):
        if n.origin != "workspace" or n.scope != "workspace":
            continue
        if n.workspace_sha and n.workspace_sha != head:
            yield LintFinding(
                code="lint/stale_workspace_nodes",
                severity="warning",
                message=(
                    f"node {n.id}: workspace_sha {n.workspace_sha} behind HEAD {head}"
                ),
                file=f"nodes/{n.id}.yaml",
                fix_hint="Run /pm-project-sync or `tripwire workspace pull`.",
            )


@register_rule(
    stage="scoping",
    code="lint/stale_workspace_nodes",
    severity="warning",
)
def _check_scoping(ctx):
    yield from _check(ctx)


@register_rule(
    stage="handoff",
    code="lint/stale_workspace_nodes",
    severity="warning",
)
def _check_handoff(ctx):
    yield from _check(ctx)
