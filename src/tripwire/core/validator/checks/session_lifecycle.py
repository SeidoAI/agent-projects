"""Session-lifecycle tripwires that gate the verified → completed route.

All four are session-scoped: they iterate ``ctx.sessions`` and gate
each session on its current status (read via the ``session_status``
enum). The canonical wiring is the route's ``controls.tripwires:``
list.

- ``v_pr_merged_for_session``     gates ``verified`` (about to flip to
                                   completed → PRs must already be
                                   merged on the remote).
- ``v_pr_review_approved``        gates ``verified``.
- ``v_session_has_developer_md``  gates each session-member issue at
                                   ``in_review`` (per the issue artifact
                                   manifest's ``required_at_status``).
- ``v_session_has_verified_md``   gates each session-member issue at
                                   ``verified``.

The first two are split out from a single artifact gate so failures
point at one file kind rather than a mixed list.

Codes (severity=error):

- ``session/pr_not_merged``
- ``session/review_not_approved``
- ``session/developer_md_missing``
- ``session/verified_md_missing``
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from tripwire.core import paths
from tripwire.core.validator._types import CheckResult, ValidationContext


def _session_at_or_past(ctx: ValidationContext, current: str, threshold: str) -> bool:
    """Return True when ``current`` ≥ ``threshold`` in the project's
    ``session_status`` enum order. Side states (paused/abandoned/...)
    are off-lifecycle and never count as "reached".
    """
    from tripwire.core.issue_artifact_store import status_at_or_past

    return status_at_or_past(
        current, threshold, ctx.project_dir, enum_name="session_status"
    )


def _issue_at_or_past(ctx: ValidationContext, current: str, threshold: str) -> bool:
    """Same as ``_session_at_or_past`` but reads the ``issue_status`` enum."""
    from tripwire.core.issue_artifact_store import status_at_or_past

    return status_at_or_past(
        current, threshold, ctx.project_dir, enum_name="issue_status"
    )


# ----------------------------------------------------------------------
# v_pr_merged_for_session
# ----------------------------------------------------------------------


def _pr_merged_for_branch(worktree_path: str, branch: str) -> bool:
    """Return True when ``branch`` has a merged PR on its origin.

    Mirrors ``session_complete._verify_pr_merged``: runs ``gh pr list
    --state merged`` from inside the worktree so the right remote is
    picked up when sessions span multiple repos. Errors are conservative
    — treated as "not merged" so the operator re-runs once the env is
    healthy rather than getting a false green.
    """
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "merged",
                "--json",
                "number",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=worktree_path,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if result.returncode != 0 or not result.stdout.strip():
        return False
    try:
        prs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return False
    return bool(prs)


def check_pr_merged_for_session(ctx: ValidationContext) -> list[CheckResult]:
    """Every worktree branch on a `verified`-or-past session must have a
    merged PR before the session can reach `completed`.

    Code: ``session/pr_not_merged``.
    """
    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session = entity.model
        sid = session.id
        if not _session_at_or_past(ctx, str(session.status), "verified"):
            continue

        runtime = getattr(session, "runtime_state", None)
        worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []
        if not worktrees:
            results.append(
                CheckResult(
                    code="session/pr_not_merged",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/session.yaml",
                    field="runtime_state.worktrees",
                    message=(
                        f"Session {sid!r} has no recorded worktrees; cannot "
                        f"verify any PR merged."
                    ),
                    fix_hint=(
                        "Restore the session's worktree records, or run "
                        "`tripwire session abandon` if the session legitimately "
                        "cannot ship."
                    ),
                )
            )
            continue

        unmerged: list[str] = []
        for wt in worktrees:
            if not _pr_merged_for_branch(wt.worktree_path, wt.branch):
                unmerged.append(wt.branch)
        if unmerged:
            results.append(
                CheckResult(
                    code="session/pr_not_merged",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/session.yaml",
                    field="runtime_state.worktrees",
                    message=(
                        f"Session {sid!r}: no merged PR found for branch(es): "
                        f"{', '.join(unmerged)}"
                    ),
                    fix_hint=(
                        "Merge the PR(s) on GitHub, or run `tripwire session "
                        "abandon` if the session legitimately cannot ship."
                    ),
                )
            )
    return results


# ----------------------------------------------------------------------
# v_pr_review_approved
# ----------------------------------------------------------------------


def _load_review_json(project_dir: Path, sid: str) -> dict[str, Any] | None:
    """Read ``sessions/<sid>/review.json`` or return None if absent/garbled."""
    from tripwire.core import paths

    review_path = paths.session_dir(project_dir, sid) / "review.json"
    if not review_path.is_file():
        return None
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def check_pr_review_approved(ctx: ValidationContext) -> list[CheckResult]:
    """Every session at `verified` or past must have a passing review.

    Reads ``sessions/<sid>/review.json`` and requires ``exit_code ≤ 1``.
    Missing/garbled file means review never ran.

    Code: ``session/review_not_approved``.
    """
    results: list[CheckResult] = []
    for entity in ctx.sessions:
        session = entity.model
        sid = session.id
        if not _session_at_or_past(ctx, str(session.status), "verified"):
            continue

        data = _load_review_json(ctx.project_dir, sid)
        if data is None:
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    message=(
                        f"Session {sid!r}: no review.json — run "
                        f"`tripwire session review {sid}` before completing."
                    ),
                    fix_hint=(
                        f"Run `tripwire session review {sid}` to produce "
                        f"review.json with a verdict and exit_code."
                    ),
                )
            )
            continue

        exit_code = data.get("exit_code")
        if not isinstance(exit_code, int):
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    field="exit_code",
                    message=(
                        f"Session {sid!r}: review.json missing a valid "
                        f"integer `exit_code`."
                    ),
                    fix_hint=(
                        f"Re-run `tripwire session review {sid}` to regenerate "
                        f"review.json."
                    ),
                )
            )
            continue

        if exit_code > 1:
            verdict = data.get("verdict", "?")
            results.append(
                CheckResult(
                    code="session/review_not_approved",
                    severity="error",
                    file=f"{paths.SESSIONS_DIR}/{sid}/review.json",
                    field="exit_code",
                    message=(
                        f"Session {sid!r}: last review reported verdict="
                        f"{verdict!r} (exit_code={exit_code}). Fix findings "
                        f"and re-review."
                    ),
                    fix_hint=(
                        "Address the review findings, then re-run "
                        f"`tripwire session review {sid}`."
                    ),
                )
            )
    return results


# ----------------------------------------------------------------------
# v_session_has_developer_md  /  v_session_has_verified_md
# ----------------------------------------------------------------------


def _issue_artifacts_for_session(
    ctx: ValidationContext, artifact_name: str
) -> list[CheckResult]:
    """Shared body: every member issue of a session must ship the named
    issue-artifact once the issue has reached the manifest's gate status.

    ``artifact_name`` selects which manifest entry — ``"developer"`` or
    ``"verified"`` — drives the check. The validator id and finding code
    are derived from the caller's choice in the public ``check_*``
    wrappers.
    """
    from tripwire.core.issue_artifact_store import load_issue_artifact_manifest
    from tripwire.core.store import load_issue

    results: list[CheckResult] = []
    try:
        manifest = load_issue_artifact_manifest(ctx.project_dir)
    except FileNotFoundError:
        return results
    except Exception:
        # Schema problems surface from check_issue_artifact_presence /
        # check_manifest_schema — don't double-fire here.
        return results

    entry = next((e for e in manifest.artifacts if e.name == artifact_name), None)
    if entry is None or not entry.required:
        return results

    code = f"session/{artifact_name}_md_missing"
    for s_entity in ctx.sessions:
        session = s_entity.model
        sid = session.id
        for issue_key in session.issues:
            try:
                issue = load_issue(ctx.project_dir, issue_key)
            except FileNotFoundError:
                continue
            if not _issue_at_or_past(ctx, issue.status, entry.required_at_status):
                continue
            artifact_path = (
                paths.issue_docs_dir(ctx.project_dir, issue_key) / entry.file
            )
            rel_path = (
                f"{paths.ISSUES_DIR}/{issue_key}/{paths.ISSUE_DOCS_SUBDIR}/{entry.file}"
            )
            if artifact_path.is_file():
                continue
            results.append(
                CheckResult(
                    code=code,
                    severity="error",
                    file=rel_path,
                    message=(
                        f"Session {sid!r} member issue {issue_key!r} ({issue.status}) "
                        f"is at-or-past {entry.required_at_status!r} but is missing "
                        f"required artifact {entry.file!r}."
                    ),
                    fix_hint=(f"Write {rel_path} from {entry.template}."),
                )
            )
    return results


def check_session_has_developer_md(ctx: ValidationContext) -> list[CheckResult]:
    """Every member issue of a session at-or-past in_review must have
    its `developer.md` artifact on disk.

    Code: ``session/developer_md_missing``.
    """
    return _issue_artifacts_for_session(ctx, "developer")


def check_session_has_verified_md(ctx: ValidationContext) -> list[CheckResult]:
    """Every member issue of a session at-or-past verified must have
    its `verified.md` artifact on disk.

    Code: ``session/verified_md_missing``.
    """
    return _issue_artifacts_for_session(ctx, "verified")


SESSION_LIFECYCLE_CHECKS = [
    check_pr_merged_for_session,
    check_pr_review_approved,
    check_session_has_developer_md,
    check_session_has_verified_md,
]


__all__ = [
    "SESSION_LIFECYCLE_CHECKS",
    "check_pr_merged_for_session",
    "check_pr_review_approved",
    "check_session_has_developer_md",
    "check_session_has_verified_md",
]
