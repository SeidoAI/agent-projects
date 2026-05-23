"""v0.7.9 §A3 — every ``follow_up`` in pm-response.yaml references an existing issue."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _pm_response_produced_at


def check_pm_response_followups_resolve(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.7.9 §A3 — every ``items[].follow_up: KUI-XX`` in pm-response.yaml
    must reference an existing issue.

    v0.11.1: gated on the manifest's `pm-response.produced_at` — fires
    only once a session has reached that lifecycle threshold. pm-response
    is PM-side output; agents at executing or in_review should not see
    this code.

    Code: ``pm_response/missing_followup``.
    """
    from tripwire.core.issue_artifact_store import status_at_or_past
    from tripwire.core.session_review_artifacts import parse_pm_response_items

    threshold = _pm_response_produced_at(ctx)
    if threshold is None:
        return []

    known_issue_ids = {entity.model.id for entity in ctx.issues}

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        if not status_at_or_past(
            str(entity.model.status),
            threshold,
            ctx.project_dir,
            enum_name="session_status",
        ):
            continue

        sid = entity.model.id
        pr_path = paths.session_dir(ctx.project_dir, sid) / "pm-response.yaml"
        if not pr_path.is_file():
            continue
        try:
            pm_items = parse_pm_response_items(pr_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # parse_error reported by check_pm_response_covers_self_review
            continue

        for item in pm_items:
            if not item.follow_up:
                continue
            if item.follow_up in known_issue_ids:
                continue
            results.append(
                CheckResult(
                    code="pm_response/missing_followup",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/pm-response.yaml",
                    message=(
                        f"pm-response.yaml references follow_up "
                        f"{item.follow_up!r}, but no such issue exists."
                    ),
                    fix_hint=(
                        "PM action — either create the follow-up issue "
                        "(`tripwire next-key --type issue`) or change "
                        "follow_up to an existing issue id."
                    ),
                )
            )

    return results
