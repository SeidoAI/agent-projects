"""Bidirectional workspace<->project link consistency check.

Tripwire workspaces and projects link two ways:

  * project side: ``project.yaml.workspace.path`` points at the
    workspace dir.
  * workspace side: ``workspace.yaml.projects[]`` lists the projects
    registered with the workspace.

This check enforces both halves agree. Drift (a project pointing at
a workspace that doesn't list it back, or vice versa) means a stale
config that the UI will silently mis-bucket. Catching it here keeps
the link a single source of truth.

Severity: ``error``. The fix is mechanical (``tripwire workspace
link``), so a hard error is the right level — silent warnings let
the inconsistency rot.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.workspace_store import load_workspace


def check_workspace_link(ctx: ValidationContext) -> list[CheckResult]:
    """Verify the project<->workspace link is consistent in both directions."""
    out: list[CheckResult] = []
    config = ctx.project_config
    if config is None or config.workspace is None or config.workspace.path is None:
        # Project intentionally has no workspace pointer — bidirectional
        # consistency only applies when the link exists. Workspaces with
        # stale entries pointing at *deleted* project dirs are caught by
        # a separate workspace-side check (out of scope here).
        return out

    pointer = config.workspace.path
    try:
        target = (ctx.project_dir / pointer).resolve()
    except OSError as exc:
        out.append(
            CheckResult(
                code="workspace/pointer_dangling",
                severity="error",
                file="project.yaml",
                field="workspace.path",
                message=(f"workspace.path={pointer!r} could not be resolved: {exc}"),
                fix_hint=(
                    "Update project.yaml.workspace.path to a real workspace "
                    "directory, or remove the pointer to mark the project "
                    "as unworkspaced."
                ),
            )
        )
        return out

    if not (target / "workspace.yaml").is_file():
        out.append(
            CheckResult(
                code="workspace/pointer_dangling",
                severity="error",
                file="project.yaml",
                field="workspace.path",
                message=(
                    f"workspace.path={pointer!r} resolves to {target} "
                    "which has no workspace.yaml."
                ),
                fix_hint=(
                    "Run `tripwire workspace link --workspace <path>` to "
                    "point at a real workspace, or scaffold the target dir "
                    "with `tripwire workspace init`."
                ),
            )
        )
        return out

    try:
        workspace = load_workspace(target)
    except (FileNotFoundError, ValueError) as exc:
        out.append(
            CheckResult(
                code="workspace/load_error",
                severity="error",
                file="project.yaml",
                field="workspace.path",
                message=f"failed to load workspace at {target}: {exc}",
                fix_hint="Inspect the workspace.yaml at the target path.",
            )
        )
        return out

    project_dir_resolved = ctx.project_dir.resolve()
    matched = _find_back_reference(workspace.projects, target, project_dir_resolved)
    if matched is None:
        out.append(
            CheckResult(
                code="workspace/back_reference_missing",
                severity="error",
                file="project.yaml",
                field="workspace.path",
                message=(
                    f"workspace at {target} doesn't list this project in its "
                    "projects[]. The link is one-way."
                ),
                fix_hint=(
                    "Run `tripwire workspace link --workspace "
                    f"{pointer}` from the project root to add the back "
                    "reference, or hand-edit "
                    f"{target}/workspace.yaml to append a "
                    "WorkspaceProjectEntry pointing at this project."
                ),
            )
        )

    return out


def _find_back_reference(
    entries: list,  # list[WorkspaceProjectEntry]
    workspace_dir: Path,
    project_dir: Path,
) -> object | None:
    """Return the entry whose path resolves to project_dir, or None.

    Entries may be relative (to the workspace dir) or absolute. Path
    comparisons go through ``resolve()`` so symlinks normalise. Uses
    plain equality rather than ``samefile`` so the check works against
    a hypothetical project dir that doesn't yet exist on disk during
    test fixtures.
    """
    for entry in entries:
        candidate = Path(entry.path)
        if not candidate.is_absolute():
            candidate = workspace_dir / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved == project_dir:
            return entry
    return None
