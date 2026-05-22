"""v0.12 — ``threshold_findings.unaddressed`` blocks the verified gate."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import (
    _at_or_past,
    _gate,
    _load_pr_review,
)


def check_pr_review_threshold_findings(ctx: ValidationContext) -> list[CheckResult]:
    """`threshold_findings.unaddressed` must be empty before transitioning
    to verified/completed. Each unaddressed entry surfaces as one finding.

    Code: ``pr_review/threshold_findings_unaddressed``.
    """
    gate = _gate(ctx)
    if gate is None:
        return []
    threshold, file = gate

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        sid = entity.model.id
        if not _at_or_past(ctx, str(entity.model.status), threshold):
            continue

        session_dir = paths.session_dir(ctx.project_dir, sid)
        data = _load_pr_review(session_dir, file)
        if data is None:
            continue

        tf = data.get("threshold_findings") or {}
        unaddressed = tf.get("unaddressed") if isinstance(tf, dict) else None
        if not isinstance(unaddressed, list) or len(unaddressed) == 0:
            continue
        for idx, item in enumerate(unaddressed):
            if not isinstance(item, dict):
                continue
            sev = item.get("severity", "?")
            cat = item.get("category", "?")
            loc = item.get("location", "?")
            reason = item.get("reason", "<no reason>")
            results.append(
                CheckResult(
                    code="pr_review/threshold_findings_unaddressed",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/{file}",
                    field=f"threshold_findings.unaddressed[{idx}]",
                    message=(
                        f"Session {sid!r}: unaddressed finding "
                        f"(severity={sev}, category={cat!r}, location={loc!r}): "
                        f"{reason}"
                    ),
                    fix_hint=(
                        "PM action — set `decision: fixed/deferred/rejected` on "
                        "this finding and provide matching evidence "
                        "(`fix_commit`, `follow_up: <KEY>`, or `note`)."
                    ),
                )
            )
    return results
