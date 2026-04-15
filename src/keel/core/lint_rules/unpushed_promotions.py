"""lint/unpushed_promotion_candidates — local nodes marked
``scope: workspace`` that haven't been pushed up yet.

Default severity is ``info``; when the project is linked to a
reachable workspace (so pushing is actionable), the per-finding
severity bumps to ``warning``. ``exit_code_for`` uses per-finding
severity, so this bump is transparent to the CLI.
"""

from __future__ import annotations

from keel.core.linter import LintFinding, register_rule
from keel.core.node_store import list_nodes


def _has_linked_workspace(ctx) -> bool:
    try:
        from keel.core.store import load_project

        cfg = load_project(ctx.project_dir)
    except Exception:  # noqa: BLE001 — malformed project.yaml; treat as no link
        return False
    if cfg.workspace is None:
        return False
    ws_dir = (ctx.project_dir / cfg.workspace.path).resolve()
    return ws_dir.exists() and (ws_dir / "workspace.yaml").is_file()


@register_rule(
    stage="scoping",
    code="lint/unpushed_promotion_candidates",
    severity="info",
)
def _check(ctx):
    has_ws = _has_linked_workspace(ctx)
    severity = "warning" if has_ws else "info"
    fix_hint = (
        "Run /pm-project-sync or `keel workspace promote <id>` to push, "
        "or mark scope=local to drop the candidacy."
        if has_ws
        else "Project isn't linked to a workspace. Link via "
        "`keel workspace link <path>` or mark scope=local."
    )
    for n in list_nodes(ctx.project_dir):
        origin = getattr(n, "origin", "local")
        scope = getattr(n, "scope", "local")
        if origin == "local" and scope == "workspace":
            yield LintFinding(
                code="lint/unpushed_promotion_candidates",
                severity=severity,
                message=(
                    f"node {n.id} is local-origin with scope=workspace "
                    "— promotion candidate."
                ),
                file=f"nodes/{n.id}.yaml",
                fix_hint=fix_hint,
            )
