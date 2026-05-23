"""v0.12 — when ``review.code_review_skill`` is set, the skill must be invoked."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import (
    _at_or_past,
    _gate,
    _get_review_config,
    _load_pr_review,
)


def check_pr_review_code_review_skill(ctx: ValidationContext) -> list[CheckResult]:
    """If `project.yaml.review.code_review_skill` is set, the
    pr-review.yaml must record an `external_reviews.code_review_skill`
    block with `invoked_at` populated.

    Code: ``pr_review/code_review_skill_missing``.
    """
    review_cfg = _get_review_config(ctx)
    skill = review_cfg.get("code_review_skill")
    if not skill:
        return []

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

        ext = data.get("external_reviews") or {}
        block = ext.get("code_review_skill") if isinstance(ext, dict) else None
        invoked = block.get("invoked_at") if isinstance(block, dict) else None
        if invoked:
            continue
        results.append(
            CheckResult(
                code="pr_review/code_review_skill_missing",
                severity="error",
                file=f"{paths.SESSIONS_DIR}/{sid}/{file}",
                field="external_reviews.code_review_skill.invoked_at",
                message=(
                    f"Session {sid!r}: project requires code-review skill "
                    f"({skill!r}) but no `external_reviews.code_review_skill."
                    f"invoked_at` is recorded in pr-review.yaml."
                ),
                fix_hint=(
                    f"PM action — invoke `{skill}` against the PR and record "
                    "the invocation time + findings (may be empty if clean) "
                    "under `external_reviews.code_review_skill`."
                ),
            )
        )
    return results
