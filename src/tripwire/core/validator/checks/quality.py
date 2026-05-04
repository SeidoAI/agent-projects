"""Project standards, phase requirements, coverage + quality heuristics."""

from __future__ import annotations

from pathlib import Path

from tripwire.core import paths
from tripwire.core.graph.refs import extract_references
from tripwire.core.id_generator import parse_key
from tripwire.core.validator._types import CheckResult, LoadedEntity, ValidationContext
from tripwire.models.issue import Issue
from tripwire.models.session import AgentSession


def _is_epic(issue) -> bool:
    """Return True if the issue has a ``type/epic`` label."""
    return any(label == "type/epic" for label in getattr(issue, "labels", []))


def check_project_standards(ctx: ValidationContext) -> list[CheckResult]:
    """V0 standards check: just confirm `<project>/standards.md` exists if any
    file references it. Future versions will read project-defined rules.
    """
    standards_path = ctx.project_dir / paths.STANDARDS
    referenced = False
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions):
        for entity in bucket:
            if paths.STANDARDS in entity.body:
                referenced = True
                break
        if referenced:
            break
    if referenced and not standards_path.exists():
        return [
            CheckResult(
                code="standards/missing",
                severity="warning",
                file=None,
                message=(
                    "An entity references standards.md, but standards.md is missing "
                    "from the project root."
                ),
            )
        ]
    return []


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


QUALITY_BODY_DEGRADATION_THRESHOLD = 0.20  # 20% drop → warning


QUALITY_REF_DEGRADATION_THRESHOLD = 0.40  # 40% drop → warning


QUALITY_MIN_ISSUES_FOR_CHECK = 9  # need 3+ per third


def check_quality_consistency(ctx: ValidationContext) -> list[CheckResult]:
    """Detect quality degradation across a writing session.

    Sorts concrete issues by key number (proxy for creation order),
    splits into first-third and last-third, and compares average body
    length and reference count.  Warns when the last-third is
    significantly thinner than the first — the "fatigue pattern" where
    agent output degrades over time.
    """
    results: list[CheckResult] = []

    # Collect concrete issues with parseable keys
    concrete: list[tuple[int, LoadedEntity]] = []
    for entity in ctx.issues:
        issue: Issue = entity.model
        if _is_epic(issue):
            continue
        try:
            _prefix, num = parse_key(issue.id)
            concrete.append((num, entity))
        except (ValueError, AttributeError):
            continue

    if len(concrete) < QUALITY_MIN_ISSUES_FOR_CHECK:
        return results

    # Sort by key number (creation order proxy)
    concrete.sort(key=lambda x: x[0])
    third = len(concrete) // 3

    first_third = concrete[:third]
    last_third = concrete[-third:]

    # --- Body character comparison ---
    first_avg_chars = sum(len(e.body) for _, e in first_third) / len(first_third)
    last_avg_chars = sum(len(e.body) for _, e in last_third) / len(last_third)

    if first_avg_chars > 0:
        body_drop = (first_avg_chars - last_avg_chars) / first_avg_chars
        if body_drop > QUALITY_BODY_DEGRADATION_THRESHOLD:
            results.append(
                CheckResult(
                    code="quality/body_degradation",
                    severity="warning",
                    message=(
                        f"Issue body quality degrades over the session. "
                        f"First-third concrete issues average {first_avg_chars:.0f} chars; "
                        f"last-third average {last_avg_chars:.0f} chars "
                        f"({body_drop:.0%} shorter). "
                        f"Reread and expand later issues to match the depth of earlier ones."
                    ),
                    fix_hint=(
                        "Run the quality calibration checkpoint: reread your first 3 "
                        "and last 3 concrete issues, rewrite the last 3 if thinner."
                    ),
                )
            )

    # --- Reference count comparison ---
    first_avg_refs = sum(
        len(set(extract_references(e.body))) for _, e in first_third
    ) / len(first_third)
    last_avg_refs = sum(
        len(set(extract_references(e.body))) for _, e in last_third
    ) / len(last_third)

    if first_avg_refs > 0:
        ref_drop = (first_avg_refs - last_avg_refs) / first_avg_refs
        if ref_drop > QUALITY_REF_DEGRADATION_THRESHOLD:
            results.append(
                CheckResult(
                    code="quality/ref_degradation",
                    severity="warning",
                    message=(
                        f"Node reference density degrades over the session. "
                        f"First-third concrete issues average {first_avg_refs:.1f} "
                        f"unique [[refs]]; last-third average {last_avg_refs:.1f} "
                        f"({ref_drop:.0%} fewer). "
                        f"Add missing [[node-id]] references to later issues."
                    ),
                    fix_hint=(
                        "Run the quality calibration checkpoint: reread your first 3 "
                        "and last 3 concrete issues, rewrite the last 3 if thinner."
                    ),
                )
            )

    return results


def check_coverage_heuristics(ctx: ValidationContext) -> list[CheckResult]:
    """Coverage warnings — hint at potential semantic gaps."""
    results: list[CheckResult] = []

    # Build reference counts from issue bodies
    node_ids = {e.raw_frontmatter.get("id", "") for e in ctx.nodes}
    node_ref_counts: dict[str, int] = dict.fromkeys(node_ids, 0)

    for entity in ctx.issues:
        refs = extract_references(entity.body)
        issue_has_node_ref = False
        for ref in refs:
            if ref in node_ref_counts:
                node_ref_counts[ref] += 1
                issue_has_node_ref = True
        if not issue_has_node_ref and entity.body.strip():
            results.append(
                CheckResult(
                    code="coverage/no_nodes_referenced",
                    severity="warning",
                    file=entity.rel_path,
                    message=(
                        "Issue body contains no [[node-id]] references. "
                        "Consider linking to relevant concept nodes."
                    ),
                )
            )

    for nid, count in node_ref_counts.items():
        if count <= 1 and nid:
            node_entity = next(
                (e for e in ctx.nodes if e.raw_frontmatter.get("id") == nid),
                None,
            )
            if node_entity:
                results.append(
                    CheckResult(
                        code="coverage/unreferenced_node",
                        severity="warning",
                        file=node_entity.rel_path,
                        message=(
                            f"Concept node '{nid}' is referenced by only "
                            f"{count} issue(s). Consider whether other issues "
                            f"should reference it, or merge it."
                        ),
                    )
                )

    return results
