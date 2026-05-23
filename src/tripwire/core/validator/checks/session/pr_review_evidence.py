"""v0.12 — every AC in ``pr-review.yaml`` carries substantive ``verified_by``."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import (
    _at_or_past,
    _gate,
    _is_placeholder,
    _load_pr_review,
)


def check_pr_review_evidence(ctx: ValidationContext) -> list[CheckResult]:
    """Every AC in pr-review.yaml must have substantive `verified_by`
    evidence — concrete file:line citations or short evidence strings,
    not placeholders.

    Code: ``pr_review/missing_evidence``.
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
            # Presence is enforced by check_artifact_presence; parse errors
            # surface there too. Don't double-fire.
            continue

        for issue in data.get("issues") or []:
            if not isinstance(issue, dict):
                continue
            issue_key = issue.get("key", "<unknown>")
            for idx, ac in enumerate(issue.get("acs") or []):
                if not isinstance(ac, dict):
                    continue
                evidence = ac.get("verified_by")
                if not isinstance(evidence, list) or len(evidence) == 0:
                    results.append(
                        CheckResult(
                            code="pr_review/missing_evidence",
                            severity="error",
                            file=f"{paths.SESSIONS_DIR}/{sid}/{file}",
                            field=f"issues[{issue_key}].acs[{idx}].verified_by",
                            message=(
                                f"Session {sid!r}, issue {issue_key!r}, AC #{idx} "
                                f"has empty `verified_by` — placeholder or skipped review."
                            ),
                            fix_hint=(
                                "PM action — replace the empty array with concrete "
                                "file:line citations or short evidence strings."
                            ),
                        )
                    )
                    continue
                for j, item in enumerate(evidence):
                    if not isinstance(item, str) or _is_placeholder(item):
                        results.append(
                            CheckResult(
                                code="pr_review/missing_evidence",
                                severity="error",
                                file=f"{paths.SESSIONS_DIR}/{sid}/{file}",
                                field=f"issues[{issue_key}].acs[{idx}].verified_by[{j}]",
                                message=(
                                    f"Session {sid!r}, issue {issue_key!r}, AC #{idx} "
                                    f"`verified_by[{j}]` is a placeholder: "
                                    f"{item!r}."
                                ),
                                fix_hint=(
                                    "PM action — replace placeholder with a concrete "
                                    "file:line citation or short evidence string."
                                ),
                            )
                        )
    return results
