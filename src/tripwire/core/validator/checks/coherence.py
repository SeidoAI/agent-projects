"""Cross-entity coherence: freshness, comments, session-issue alignment, pm-response."""

from __future__ import annotations

from tripwire.core import freshness as freshness_mod
from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.models.comment import Comment
from tripwire.models.session import AgentSession

# v0.7b Layer-3 coherence matrix — spec §6.4.
#
# Matrix is keyed by *phase* (5 values per spec table), not by the full
# SessionStatus enum. SessionStatus values map to a phase via
# _SESSION_STATUS_TO_PHASE. Session statuses not in the mapping are
# off-lifecycle (failed, paused, abandoned, re_engaged, waiting_for_*)
# and skip coherence checking entirely.
#
# Verdict:
#   "ok"           — aligned
#   "ahead_warn"   — issue later in lifecycle than session; surfaces as
#                    `coherence/issue_status_ahead_of_session` (warning).
#   "behind_error" — issue earlier than session; surfaces as
#                    `coherence/issue_status_lags_session` (error).
#
# Spec §6.4 table:
#   planned      → warn on later
#   in_progress  → warn on later
#   in_review    → error on earlier
#   verified     → error on earlier
#   done         → error on anything else

_SESSION_STATUS_TO_PHASE: dict[str, str] = {
    "planned": "planned",
    # Working states (queued waiting to launch, executing locally, active
    # in orchestrator) all represent the in_progress phase.
    "queued": "in_progress",
    "executing": "in_progress",
    "active": "in_progress",
    "in_review": "in_review",
    "verified": "verified",
    # completed = tripwire session's terminal state = phase `done`.
    "completed": "done",
    # Off-lifecycle statuses (failed, paused, abandoned, re_engaged,
    # waiting_for_*) deliberately omitted — coherence is meaningless there.
}

_COHERENCE_MATRIX: dict[str, dict[str, str]] = {
    "planned": {
        "backlog": "ok",
        "todo": "ok",
        "in_progress": "ahead_warn",
        "in_review": "ahead_warn",
        "verified": "ahead_warn",
        "done": "ahead_warn",
    },
    "in_progress": {
        "backlog": "behind_error",
        "todo": "ok",
        "in_progress": "ok",
        "in_review": "ok",
        "verified": "ahead_warn",
        "done": "ahead_warn",
    },
    "in_review": {
        "backlog": "behind_error",
        "todo": "behind_error",
        "in_progress": "behind_error",
        "in_review": "ok",
        "verified": "ok",
        "done": "ok",
    },
    "verified": {
        "backlog": "behind_error",
        "todo": "behind_error",
        "in_progress": "behind_error",
        "in_review": "behind_error",
        "verified": "ok",
        "done": "ok",
    },
    "done": {
        "backlog": "behind_error",
        "todo": "behind_error",
        "in_progress": "behind_error",
        "in_review": "behind_error",
        "verified": "behind_error",
        "done": "ok",
    },
}


def check_freshness(ctx: ValidationContext) -> list[CheckResult]:
    """Concept node freshness — content_hash must match live content."""
    if ctx.project_config is None:
        return []
    results: list[CheckResult] = []
    nodes = [e.model for e in ctx.nodes]
    rel_by_id = {e.model.id: e.rel_path for e in ctx.nodes}
    for fr in freshness_mod.check_all_nodes(nodes, ctx.project_config):
        rel = rel_by_id.get(fr.node_id, f"{paths.NODES_DIR}/{fr.node_id}.yaml")
        if fr.status == freshness_mod.FreshnessStatus.SOURCE_MISSING:
            results.append(
                CheckResult(
                    code="freshness/source_missing",
                    severity="error",
                    file=rel,
                    field="source",
                    message=fr.detail or f"Source missing for node {fr.node_id}.",
                )
            )
        elif fr.status == freshness_mod.FreshnessStatus.STALE:
            results.append(
                CheckResult(
                    code="freshness/stale",
                    severity="warning",
                    file=rel,
                    field="source.content_hash",
                    message=fr.detail or f"Node {fr.node_id} content_hash is stale.",
                    fix_hint="Run `tripwire node check --update` (deferred to a later release).",
                )
            )
    return results


def check_comment_provenance(ctx: ValidationContext) -> list[CheckResult]:
    """Every comment has author/type/created_at; type is in the active enum."""
    results: list[CheckResult] = []
    for entity in ctx.comments:
        comment: Comment = entity.model
        if not comment.author:
            results.append(
                CheckResult(
                    code="comment/no_author",
                    severity="error",
                    file=entity.rel_path,
                    field="author",
                    message="Comment is missing required field `author`.",
                )
            )
        if not comment.type:
            results.append(
                CheckResult(
                    code="comment/no_type",
                    severity="error",
                    file=entity.rel_path,
                    field="type",
                    message="Comment is missing required field `type`.",
                )
            )
        if comment.created_at is None:
            results.append(
                CheckResult(
                    code="comment/no_created_at",
                    severity="error",
                    file=entity.rel_path,
                    field="created_at",
                    message="Comment is missing required field `created_at`.",
                )
            )
    return results


def check_session_issue_coherence(ctx: ValidationContext) -> list[CheckResult]:
    """Layer-3 coherence: session.status vs. referenced issue statuses.

    Emits `coherence/issue_status_lags_session` (error) when an issue is
    behind where the session claims it should be; and
    `coherence/issue_status_ahead_of_session` (warning) when an issue is
    further along than the session stage would suggest.

    Sessions in statuses not listed in the matrix (`failed`, `waiting_for_*`,
    `paused`, `abandoned`, `re_engaged`) are skipped — those are off-lifecycle
    states where alignment isn't meaningful.
    """
    results: list[CheckResult] = []
    issues_by_key = {entity.model.id: entity.model for entity in ctx.issues}
    for entity in ctx.sessions:
        session: AgentSession = entity.model
        phase = _SESSION_STATUS_TO_PHASE.get(session.status)
        if phase is None:
            continue
        session_row = _COHERENCE_MATRIX[phase]
        for issue_key in session.issues:
            issue = issues_by_key.get(issue_key)
            if issue is None:
                continue
            verdict = session_row.get(issue.status, "ok")
            if verdict == "ok":
                continue
            if verdict == "behind_error":
                code = "coherence/issue_status_lags_session"
                severity = "error"
                direction = "issue lags session"
            else:  # "ahead_warn"
                code = "coherence/issue_status_ahead_of_session"
                severity = "warning"
                direction = "issue is ahead of session"
            results.append(
                CheckResult(
                    code=code,
                    severity=severity,
                    file=entity.rel_path,
                    field="status",
                    message=(
                        f"Session {session.id!r} ({session.status}) has issue "
                        f"{issue_key!r} at {issue.status!r} — {direction}."
                    ),
                    fix_hint=(
                        "Advance the issue status to match, or step the session "
                        "status back to a phase that matches the issue."
                    ),
                )
            )
    return results


def check_pm_response_covers_self_review(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.7.9 §A3 — every self-review.md bullet must have a matching
    quote_excerpt in pm-response.yaml.

    Substring match (case-insensitive, both directions). Strict
    enough to catch "PM skipped read entirely," loose enough to not
    be a transcription chore.

    Codes:
      - ``pm_response/missing_file`` — self-review present, pm-response absent
      - ``pm_response/parse_error``  — pm-response.yaml unparseable
      - ``pm_response/incomplete_coverage`` — bullet has no matching quote_excerpt
    """
    from tripwire.core.session_review_artifacts import (
        parse_pm_response_items,
        parse_self_review_items,
    )

    results: list[CheckResult] = []

    for entity in ctx.sessions:
        sid = entity.model.id
        sdir = ctx.project_dir / "sessions" / sid
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
                    file=f"sessions/{sid}/self-review.md",
                    message=f"Could not read self-review.md: {exc}",
                )
            )
            continue
        if not sr_items:
            continue

        pr_path = sdir / "pm-response.yaml"
        if not pr_path.is_file():
            results.append(
                CheckResult(
                    code="pm_response/missing_file",
                    severity="error",
                    file=f"sessions/{sid}/pm-response.yaml",
                    message=(
                        f"Session {sid!r} has self-review.md but no "
                        "pm-response.yaml; PM has not recorded a response."
                    ),
                    fix_hint=(
                        "Author sessions/<sid>/pm-response.yaml from "
                        "templates/artifacts/pm-response.yaml.j2 "
                        "(`tripwire session scaffold <sid> "
                        "--artifact pm-response.yaml`)."
                    ),
                )
            )
            continue

        try:
            pm_items = parse_pm_response_items(pr_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            results.append(
                CheckResult(
                    code="pm_response/parse_error",
                    severity="error",
                    file=f"sessions/{sid}/pm-response.yaml",
                    message=f"pm-response.yaml could not be parsed: {exc}",
                    fix_hint="Check YAML syntax against the template.",
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
                    file=f"sessions/{sid}/pm-response.yaml",
                    message=(
                        f"Self-review item under Lens {sr.lens} has no "
                        f"matching quote_excerpt in pm-response.yaml: "
                        f"{sr.text!r}"
                    ),
                    fix_hint=(
                        "Add an items[] entry to pm-response.yaml with a "
                        "quote_excerpt that contains a substring of this "
                        "self-review bullet."
                    ),
                )
            )

    return results


def check_pm_response_followups_resolve(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.7.9 §A3 — every ``items[].follow_up: KUI-XX`` in pm-response.yaml
    must reference an existing issue.

    Code: ``pm_response/missing_followup``.
    """
    from tripwire.core.session_review_artifacts import parse_pm_response_items

    known_issue_ids = {entity.model.id for entity in ctx.issues}

    results: list[CheckResult] = []
    for entity in ctx.sessions:
        sid = entity.model.id
        pr_path = ctx.project_dir / "sessions" / sid / "pm-response.yaml"
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
                    file=f"sessions/{sid}/pm-response.yaml",
                    message=(
                        f"pm-response.yaml references follow_up "
                        f"{item.follow_up!r}, but no such issue exists."
                    ),
                    fix_hint=(
                        "Either create the follow-up issue (`tripwire "
                        "next-key --type issue`) or change follow_up to "
                        "an existing issue id."
                    ),
                )
            )

    return results
