"""Anti-fatigue heuristic: degraded body/ref density over the writing session."""

from __future__ import annotations

from tripwire.core.graph.refs import extract_references
from tripwire.core.id_generator import parse_key
from tripwire.core.validator._types import CheckResult, LoadedEntity, ValidationContext
from tripwire.models.issue import Issue


def _is_epic(issue) -> bool:
    """Return True if the issue has a ``type/epic`` label."""
    return any(label == "type/epic" for label in getattr(issue, "labels", []))


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
