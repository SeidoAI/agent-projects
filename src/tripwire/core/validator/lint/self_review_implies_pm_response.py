"""v0.7.9 §A9 — self-review.md on main ⇒ pm-response.yaml on main.

Catches the "PM forgot to respond" state: a session whose author
finished and pushed self-review, but the PM never wrote the closing
response. Triggered by the presence of self-review.md on origin/main
for any known session, regardless of session.status.

KUI-86's ``check_pm_response_covers_self_review`` enforces the same
contract on the *local* working tree (so missing pm-response.yaml is
caught pre-merge); this rule is the post-merge mirror — we want main
itself to never carry an unanswered self-review.

Offline-degradation pattern: emit one ``main_unavailable`` warning if
origin/main is unreadable and skip per-session checks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from tripwire.core.git_helpers import MainTreeUnavailable, list_paths_on_main
from tripwire.core.store import PROJECT_CONFIG_FILENAME

if TYPE_CHECKING:
    from tripwire.core.validator import CheckResult, ValidationContext


def check(ctx: ValidationContext) -> list[CheckResult]:
    from tripwire.core.validator import CheckResult

    if not ctx.sessions:
        return []

    try:
        on_main = list_paths_on_main(ctx.project_dir)
    except MainTreeUnavailable as exc:
        return [
            CheckResult(
                code="self_review_implies_pm_response/main_unavailable",
                severity="warning",
                file=PROJECT_CONFIG_FILENAME,
                message=(
                    f"Cannot read origin/main; "
                    f"`self-review ⇒ pm-response` rule unverified ({exc})."
                ),
                fix_hint=(
                    "Run `git fetch origin` in the project tracking repo, "
                    "then re-run validate."
                ),
            )
        ]

    # v0.12: consult the manifest for both filenames so project overrides
    # (e.g. renamed `self-review` artifact, custom PM response file) are
    # respected. Fall back to canonical defaults when an entry isn't
    # manifested — keeps the rule meaningful for projects with sparse
    # manifests, while still picking up manifest renames when present.
    from tripwire.core.validator._manifest_lookup import artifact_entry

    self_review_entry = artifact_entry(ctx, "self-review")
    pm_response_entry = artifact_entry(ctx, "pm-response")
    self_review_file = (
        self_review_entry.file if self_review_entry is not None else "self-review.md"
    )
    pm_response_file = (
        pm_response_entry.file if pm_response_entry is not None else "pm-response.yaml"
    )

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        sid = entity.model.id
        # Two layouts coexist in the wild; check both before reporting.
        sr_candidates = (
            f"sessions/{sid}/{self_review_file}",
            f"sessions/{sid}/artifacts/{self_review_file}",
        )
        pr_candidates = (
            f"sessions/{sid}/{pm_response_file}",
            f"sessions/{sid}/artifacts/{pm_response_file}",
        )
        if not any(p in on_main for p in sr_candidates):
            continue
        if any(p in on_main for p in pr_candidates):
            continue
        # Quote the canonical (non-nested) path in user-facing messages.
        pm_response = pr_candidates[0]
        results.append(
            CheckResult(
                code="self_review_implies_pm_response/missing_pm_response",
                severity="error",
                file=entity.rel_path,
                message=(
                    f"Session {sid!r} has {self_review_file} on origin/main "
                    f"but {pm_response!r} is missing — the PM has not "
                    f"closed the loop."
                ),
                fix_hint=(
                    f"PM action — author and commit {pm_response} on the "
                    f"project tracking branch, then merge to main."
                ),
            )
        )

    return results
