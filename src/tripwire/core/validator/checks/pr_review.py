"""v0.12 — PM-review enforcement (handoff #3 fix).

Four validator rules that gate the substance of `pr-review.yaml`. The
artifact's *presence* is enforced by `check_artifact_presence` via the
manifest entry's `produced_at: in_review`; these rules check that the
file's content is real (not placeholder), that threshold findings are
addressed, and that configured external-reviewer / code-review-skill
signals are recorded.

All four rules are gated on the `pr-review` manifest entry's
`produced_at` (i.e. they only fire on sessions at-or-past in_review).

Codes (all severity=error, prefix `pr_review/`):

- ``pr_review/missing_evidence`` — an AC's `verified_by` is empty or
  contains placeholder text.
- ``pr_review/threshold_findings_unaddressed`` —
  `threshold_findings.unaddressed` is non-empty.
- ``pr_review/external_reviewer_missing`` —
  `project.yaml.review.external_reviewer_mention` is set AND
  `external_reviews.codex.comment_url` is missing/empty.
- ``pr_review/code_review_skill_missing`` —
  `project.yaml.review.code_review_skill` is set AND
  `external_reviews.code_review_skill.invoked_at` is missing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext

_PLACEHOLDER_PATTERNS = [
    re.compile(r"^manual verification needed$", re.IGNORECASE),
    re.compile(r"^<.*>$"),  # < anything > placeholder
    re.compile(r"^tbd$", re.IGNORECASE),
    re.compile(r"^todo$", re.IGNORECASE),
    re.compile(r"^—$"),  # em-dash
    re.compile(r"^-$"),
]
"""Regex patterns recognised as placeholder text in `verified_by`.

Any AC whose `verified_by` array is empty, OR contains an entry
matching any of these patterns, OR contains an entry shorter than 8
characters, fails the missing_evidence check.
"""


def _is_placeholder(evidence: str) -> bool:
    """Is this `verified_by` string a placeholder?"""
    s = (evidence or "").strip()
    if len(s) < 8:
        return True
    return any(p.match(s) for p in _PLACEHOLDER_PATTERNS)


def _load_pr_review(session_dir: Path, file: str) -> dict[str, Any] | None:
    """Read pr-review.yaml from either layout. Returns parsed dict or None."""
    from tripwire.core.validator._manifest_lookup import find_artifact_on_disk

    path = find_artifact_on_disk(session_dir, file)
    if path is None:
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _gate(ctx: ValidationContext) -> tuple[str, str] | None:
    """Look up the pr-review manifest entry and return
    `(threshold, file)` for callers to gate on. Returns None if the
    entry isn't manifested (skip check)."""
    from tripwire.core.validator._manifest_lookup import artifact_entry

    entry = artifact_entry(ctx, "pr-review")
    if entry is None:
        return None
    return entry.produced_at, entry.file


def _at_or_past(ctx: ValidationContext, status: str, threshold: str) -> bool:
    """Wraps `status_at_or_past` with the artifact_phase → session_status
    mapping and the session_status enum."""
    from tripwire.core.issue_artifact_store import status_at_or_past
    from tripwire.core.validator._manifest_lookup import phase_to_session_status

    return status_at_or_past(
        status,
        phase_to_session_status(threshold),
        ctx.project_dir,
        enum_name="session_status",
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


def _get_review_config(ctx: ValidationContext) -> dict[str, Any]:
    """Read `project.yaml.review` as a plain dict for graceful fallback
    (older projects without the v0.12 field still validate)."""
    if ctx.project_config is None:
        return {}
    review = getattr(ctx.project_config, "review", None)
    if review is None:
        return {}
    if hasattr(review, "model_dump"):
        return review.model_dump()
    return dict(review) if isinstance(review, dict) else {}


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
