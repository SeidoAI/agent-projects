"""v0.12 — when ``review.external_reviewer_mention`` is set, codex must comment."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import (
    _at_or_past,
    _gate,
    _get_review_config,
    _load_pr_review,
)


def check_pr_review_external_reviewer(ctx: ValidationContext) -> list[CheckResult]:
    """If `project.yaml.review.external_reviewer_mention` is set, the
    pr-review.yaml must record a `external_reviews.codex.comment_url`.

    Code: ``pr_review/external_reviewer_missing``.
    """
    review_cfg = _get_review_config(ctx)
    mention = review_cfg.get("external_reviewer_mention")
    if not mention:
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
        codex = ext.get("codex") if isinstance(ext, dict) else None
        url = codex.get("comment_url") if isinstance(codex, dict) else None
        if url:
            continue
        results.append(
            CheckResult(
                code="pr_review/external_reviewer_missing",
                severity="error",
                file=f"{paths.SESSIONS_DIR}/{sid}/{file}",
                field="external_reviews.codex.comment_url",
                message=(
                    f"Session {sid!r}: project requires external-reviewer mention "
                    f"({mention!r}) but no `external_reviews.codex.comment_url` "
                    f"is recorded in pr-review.yaml."
                ),
                fix_hint=(
                    f"PM action — post `{mention}` on the PR (`gh pr comment "
                    f'<pr> --body "{mention} please review"`) and record the '
                    f"comment URL under `external_reviews.codex.comment_url`."
                ),
            )
        )
    return results
