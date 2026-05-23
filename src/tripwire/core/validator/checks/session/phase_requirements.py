"""Phase-specific artifact requirements (scoping-plan, gap-analysis, compliance)."""

from __future__ import annotations

from pathlib import Path

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.session import AgentSession

_SCOPING_PLAN_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/scoping-plan.md"


_GAP_ANALYSIS_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/gap-analysis.md"


_COMPLIANCE_PATH = f"{paths.PLANS_ARTIFACTS_DIR}/compliance.md"


def _artifact_status(project_dir: Path, rel_path: str) -> str | None:
    """Return the status marker from a meta-artifact, or None if missing.

    Artifacts use a ``<!-- status: complete -->`` HTML comment on any line
    to signal completion.  Returns ``"complete"``, ``"incomplete"``, or
    ``None`` (file doesn't exist or is empty).
    """
    full = project_dir / rel_path
    if not full.is_file():
        return None
    text = full.read_text(encoding="utf-8").strip()
    if not text:
        return None
    if "<!-- status: complete -->" in text:
        return "complete"
    return "incomplete"


def check_phase_requirements(ctx: ValidationContext) -> list[CheckResult]:
    """Enforce phase-specific requirements.

    - **scoping**: ``scoping-plan.md`` must exist.
    - **scoped**: ``gap-analysis.md`` and ``compliance.md`` must exist
      and be marked ``complete``.  All sessions must have ``plan.md``.
    - **executing** / **reviewing**: same as scoped.
    """
    from tripwire.models.project import ProjectPhase

    if ctx.project_config is None:
        return []

    phase = ctx.project_config.phase
    results: list[CheckResult] = []

    # --- scoping: scoping-plan.md expected once entities exist ---------
    if phase == ProjectPhase.scoping and ctx.issues:
        status = _artifact_status(ctx.project_dir, _SCOPING_PLAN_PATH)
        if status is None:
            results.append(
                CheckResult(
                    code="phase/missing_artifact",
                    severity="warning",
                    file=_SCOPING_PLAN_PATH,
                    message=(
                        "Issues exist but no scoping plan found. "
                        "Write the scoping plan before creating entities."
                    ),
                )
            )

    # --- scoped and beyond: gap-analysis + compliance required --------
    if phase in (
        ProjectPhase.scoped,
        ProjectPhase.executing,
        ProjectPhase.reviewing,
    ):
        for artifact_path, label in (
            (_GAP_ANALYSIS_PATH, "gap analysis"),
            (_COMPLIANCE_PATH, "compliance checklist"),
        ):
            status = _artifact_status(ctx.project_dir, artifact_path)
            if status is None:
                results.append(
                    CheckResult(
                        code="phase/missing_artifact",
                        severity="error",
                        file=artifact_path,
                        message=(
                            f"Phase '{phase.value}' requires {artifact_path}. "
                            f"Complete the {label} before advancing to this phase."
                        ),
                    )
                )
            elif status == "incomplete":
                results.append(
                    CheckResult(
                        code="phase/incomplete_artifact",
                        severity="error",
                        file=artifact_path,
                        message=(
                            f"{artifact_path} exists but is not marked complete. "
                            f"Add '<!-- status: complete -->' when finished."
                        ),
                    )
                )

        # All sessions must have plan.md. Iterate ctx.sessions (loaded by
        # _load_sessions) instead of re-globbing the filesystem.
        for entity in ctx.sessions:
            session: AgentSession = entity.model
            plan = paths.session_plan_path(ctx.project_dir, session.id)
            if not plan.is_file():
                results.append(
                    CheckResult(
                        code="phase/missing_session_plan",
                        severity="error",
                        file=(
                            f"{paths.SESSIONS_DIR}/{session.id}/{paths.SESSION_PLAN}"
                        ),
                        message=(
                            f"Session {session.id!r} has no "
                            f"{paths.SESSION_PLAN}. All sessions must have "
                            f"plans before phase '{phase.value}'."
                        ),
                    )
                )

    return results
