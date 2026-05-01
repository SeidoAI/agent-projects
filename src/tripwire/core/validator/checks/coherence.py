"""Cross-entity coherence: freshness, comments, session-issue alignment, pm-response."""

from __future__ import annotations

from tripwire.core import freshness as freshness_mod
from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext
from tripwire.core.workflow.registry import registers_at
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

# v0.9.4: keys here are canonical session-status values (post-rename).
# Pre-v0.9.4 names ("active", "waiting_for_*", "re_engaged") normalise via
# ``SessionStatus.__missing__`` before reaching this lookup.
_SESSION_STATUS_TO_PHASE: dict[str, str] = {
    "planned": "planned",
    "queued": "executing",
    "executing": "executing",
    "in_review": "in_review",
    "verified": "verified",
    "completed": "completed",
    # Off-lifecycle statuses (failed, paused, abandoned) are deliberately
    # omitted — coherence is meaningless there.
}

# v0.9.4: phase keys + issue-state keys are canonical (planned, queued,
# executing, in_review, verified, completed). Legacy issue names
# (backlog, todo, in_progress, done) are accepted via ``_resolve_issue_state``
# below so callers don't need to pre-normalise.
_COHERENCE_MATRIX: dict[str, dict[str, str]] = {
    "planned": {
        "planned": "ok",
        "queued": "ok",
        "executing": "ahead_warn",
        "in_review": "ahead_warn",
        "verified": "ahead_warn",
        "completed": "ahead_warn",
    },
    "executing": {
        "planned": "behind_error",
        "queued": "ok",
        "executing": "ok",
        "in_review": "ok",
        "verified": "ahead_warn",
        "completed": "ahead_warn",
    },
    "in_review": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "ok",
        "verified": "ok",
        "completed": "ok",
    },
    "verified": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "behind_error",
        "verified": "ok",
        "completed": "ok",
    },
    "completed": {
        "planned": "behind_error",
        "queued": "behind_error",
        "executing": "behind_error",
        "in_review": "behind_error",
        "verified": "behind_error",
        "completed": "ok",
    },
}


def _resolve_issue_state(value: str) -> str:
    """Map legacy / alias issue-status strings to canonical for matrix lookup."""
    from tripwire.core.status_contract import normalize_issue_status

    return normalize_issue_status(value)


def _resolve_session_state(value: str) -> str:
    """Map legacy / alias session-status strings to canonical for matrix lookup."""
    from tripwire.core.status_contract import normalize_session_status

    return normalize_session_status(value)


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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


@registers_at("coding-session", "executing")
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
        phase = _SESSION_STATUS_TO_PHASE.get(_resolve_session_state(session.status))
        if phase is None:
            continue
        session_row = _COHERENCE_MATRIX[phase]
        for issue_key in session.issues:
            issue = issues_by_key.get(issue_key)
            if issue is None:
                continue
            verdict = session_row.get(_resolve_issue_state(issue.status), "ok")
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


# v0.9.4 — issue ↔ session status contract checks. Both check the same
# invariant from different angles:
#   * ``check_issue_session_status_compatibility`` (error): for each
#     session, every member issue's status must be in the allowed set
#     for the session's state, per
#     ``status_contract.ALLOWED_ISSUE_STATES_BY_SESSION_STATE``.
#   * ``check_done_implies_session_completed`` (warn): an issue at
#     ``completed`` belongs to at least one ``completed`` session — flags
#     "orphan completion" cases where the closeout sweep didn't run.


@registers_at("coding-session", "executing")
def check_issue_session_status_compatibility(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.9.4 contract: every member issue's status must be in the set
    allowed for its session's status. Catches contract violations on write.
    """
    from tripwire.core.status_contract import (
        ALLOWED_ISSUE_STATES_BY_SESSION_STATE,
        is_issue_state_compatible_with_session_state,
        normalize_session_status,
    )

    results: list[CheckResult] = []
    issues_by_key = {entity.model.id: entity for entity in ctx.issues}
    for session_entity in ctx.sessions:
        session = session_entity.model
        s_state = normalize_session_status(str(session.status))
        if s_state not in ALLOWED_ISSUE_STATES_BY_SESSION_STATE:
            # Unknown session state — not our problem here. Other checks
            # cover unknown enum values.
            continue
        for issue_key in session.issues:
            issue_entity = issues_by_key.get(issue_key)
            if issue_entity is None:
                continue
            issue = issue_entity.model
            if not is_issue_state_compatible_with_session_state(
                str(session.status), str(issue.status)
            ):
                allowed = sorted(
                    ALLOWED_ISSUE_STATES_BY_SESSION_STATE[s_state]
                )
                results.append(
                    CheckResult(
                        code="contract/issue_session_state_incompatible",
                        severity="error",
                        file=session_entity.rel_path,
                        field="status",
                        message=(
                            f"Session {session.id!r} ({session.status}) has "
                            f"issue {issue_key!r} at {issue.status!r} — "
                            f"not in the allowed set for session state "
                            f"{s_state!r}: {allowed}."
                        ),
                        fix_hint=(
                            "Sweep the session forward via "
                            "`tripwire session transition --sweep-issues`, "
                            "or advance the issue status to match the "
                            "contract."
                        ),
                    )
                )
    return results


@registers_at("coding-session", "executing")
def check_done_implies_session_completed(
    ctx: ValidationContext,
) -> list[CheckResult]:
    """v0.9.4 warning: an issue at ``completed`` should belong to at
    least one session that's also ``completed`` (or no session at all).

    Catches "orphan completion" cases where an issue was flipped to
    completed manually without the session being walked through to its
    own terminal state.
    """
    from tripwire.core.status_contract import (
        normalize_issue_status,
        normalize_session_status,
    )

    results: list[CheckResult] = []
    sessions_by_issue: dict[str, list[str]] = {}
    for session_entity in ctx.sessions:
        session = session_entity.model
        s_state = normalize_session_status(str(session.status))
        for issue_key in session.issues:
            sessions_by_issue.setdefault(issue_key, []).append(s_state)

    for entity in ctx.issues:
        issue = entity.model
        i_state = normalize_issue_status(str(issue.status))
        if i_state != "completed":
            continue
        owning_states = sessions_by_issue.get(issue.id, [])
        if not owning_states:
            # Issue has no sessions claiming it — orphan-completion is
            # still legitimate (e.g. closed without ever being session-owned).
            continue
        if "completed" in owning_states or "abandoned" in owning_states:
            continue
        results.append(
            CheckResult(
                code="contract/done_implies_session_completed",
                severity="warning",
                file=entity.rel_path,
                field="status",
                message=(
                    f"Issue {issue.id!r} is at 'completed' but no owning "
                    f"session is in {{completed, abandoned}}. "
                    f"Owning session states: {sorted(owning_states)}."
                ),
                fix_hint=(
                    "Walk the owning session through its terminal "
                    "transition, or move the issue back if the session "
                    "isn't actually done."
                ),
            )
        )
    return results


@registers_at("coding-session", "verified")
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


@registers_at("coding-session", "verified")
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
