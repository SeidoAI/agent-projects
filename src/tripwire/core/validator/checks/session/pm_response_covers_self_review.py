"""v0.7.9 §A3 — every self-review.md bullet has a matching pm-response excerpt."""

from __future__ import annotations

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.validator.checks._helpers import _pm_response_produced_at


def check_pm_response_covers_self_review(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.7.9 §A3 — every self-review.md bullet must have a matching
    quote_excerpt in pm-response.yaml.

    Substring match (case-insensitive, both directions). Strict
    enough to catch "PM skipped read entirely," loose enough to not
    be a transcription chore.

    v0.11.1: gated on the manifest's `pm-response.produced_at` — only
    fires once a session reaches that lifecycle threshold. Default
    manifest declares `produced_at: completed`, so agents at executing
    or in_review never see these findings (`pm-response.yaml` is PM-side
    output). Missing-file enforcement is delegated to `check_artifact_presence`.

    Codes:
      - ``pm_response/io_error``           — self-review.md unreadable
      - ``pm_response/parse_error``        — pm-response.yaml unparseable
      - ``pm_response/incomplete_coverage``— bullet has no matching quote_excerpt
    """
    from tripwire.core.issue_artifact_store import status_at_or_past
    from tripwire.core.session_review_artifacts import (
        parse_pm_response_items,
        parse_self_review_items,
    )

    threshold = _pm_response_produced_at(ctx)
    if threshold is None:
        return []

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
        sdir = paths.session_dir(ctx.project_dir, sid)
        sr_path = sdir / "self-review.md"
        if not sr_path.is_file():
            # Presence is enforced by check_artifact_presence.
            continue

        try:
            sr_items = parse_self_review_items(sr_path.read_text(encoding="utf-8"))
        except OSError as exc:
            results.append(
                CheckResult(
                    code="pm_response/io_error",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/self-review.md",
                    message=f"Could not read self-review.md: {exc}",
                    fix_hint=(
                        "PM action — investigate the read failure on "
                        "self-review.md (permissions, encoding, missing "
                        "file). Agent-side artifact authoring is unrelated."
                    ),
                )
            )
            continue
        if not sr_items:
            continue

        pr_path = sdir / "pm-response.yaml"
        if not pr_path.is_file():
            # Missing file is reported by check_artifact_presence (which
            # honours the same produced_at gate). No need to duplicate.
            continue

        try:
            pm_items = parse_pm_response_items(pr_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            results.append(
                CheckResult(
                    code="pm_response/parse_error",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/pm-response.yaml",
                    message=f"pm-response.yaml could not be parsed: {exc}",
                    fix_hint=(
                        "PM action — fix YAML syntax in pm-response.yaml "
                        "(check against templates/artifacts/pm-response.yaml.j2)."
                    ),
                )
            )
            continue

        excerpts_lower = [(it.quote_excerpt or "").strip().lower() for it in pm_items]
        for sr in sr_items:
            sr_lower = sr.text.lower()
            covered = any(
                e and (e in sr_lower or sr_lower in e) for e in excerpts_lower
            )
            if covered:
                continue
            results.append(
                CheckResult(
                    code="pm_response/incomplete_coverage",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/pm-response.yaml",
                    message=(
                        f"Self-review item under Lens {sr.lens} has no "
                        f"matching quote_excerpt in pm-response.yaml: "
                        f"{sr.text!r}"
                    ),
                    fix_hint=(
                        "PM action — add an items[] entry to "
                        "pm-response.yaml with a quote_excerpt that contains "
                        "a substring of this self-review bullet."
                    ),
                )
            )

    return results
