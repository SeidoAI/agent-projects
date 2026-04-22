"""Session complete orchestration.

Gates session close-out behind: (a) session in a completable status,
(b) at least one merged PR for the session's branches, (c) every
required issue artifact present. Then closes issues, transitions the
session to `done`, and removes worktrees.

Insights application is out-of-scope here — the PM's
`/pm-session-complete` runs `tripwire session insights apply/reject`
before invoking this routine.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core import paths
from tripwire.core.issue_artifact_store import (
    load_issue_artifact_manifest,
    status_at_or_past,
)
from tripwire.core.session_store import load_session, save_session
from tripwire.core.store import load_issue, save_issue


class CompleteError(ValueError):
    """Raised when complete refuses to proceed."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class CompleteResult:
    session_id: str
    issues_closed: list[str] = field(default_factory=list)
    worktrees_removed: list[str] = field(default_factory=list)
    node_diffs: list[dict] = field(default_factory=list)
    sessions_unblocked: list[str] = field(default_factory=list)


def complete_session(
    project_dir: Path,
    session_id: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    force_review: bool = False,
    skip_artifact_check: bool = False,
    skip_worktree_cleanup: bool = False,
    skip_pr_merge_check: bool = False,
    skip_pr_flow: bool = False,
    skip_pr_flow_push: bool = False,
) -> CompleteResult:
    """Run the close-out gates then transition the session to `done`.

    Gates per spec §11.2:
      1. Status in {in_review, verified} (unless --force).
      2. PR merged (unless --force).
      3. Per-issue required artifacts present (no override; §7.3).
      4. Most recent review exit_code ≤ 1 (unless --force-review).
    """
    session = load_session(project_dir, session_id)
    result = CompleteResult(session_id=session_id)

    # Spec §11.2 step 1 — narrow status gate. `in_progress`, `executing`,
    # `active` must go through /pm-session-review first.
    completable = {"in_review", "verified"}
    if session.status not in completable and not force:
        raise CompleteError(
            "complete/not_active",
            f"Session status is {session.status!r}; expected one of "
            f"{sorted(completable)}. Run /pm-session-review first, or pass --force.",
        )

    if not skip_pr_merge_check and not force:
        _verify_pr_merged(session)

    if not skip_artifact_check:
        _verify_issue_artifacts(project_dir, session)

    # Spec §11.2 step 4 — review exit-code gate.
    if not force and not force_review:
        _verify_review_ok(project_dir, session)

    result.node_diffs = _compute_node_diffs(project_dir, session)

    if dry_run:
        return result

    # Dual-PR flow — commit + push + PR per worktree with changes.
    if not skip_pr_flow:
        from tripwire.core.session_pr_flow import PrFlowError, run_pr_flow

        try:
            pr_result = run_pr_flow(
                session=session,
                project_dir=project_dir,
                skip_push=skip_pr_flow_push,
            )
        except PrFlowError as exc:
            raise CompleteError("complete/pr_flow_failed", str(exc)) from exc
        if pr_result.pr_urls and session.engagements:
            session.engagements[-1].pr_urls = list(pr_result.pr_urls)

    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        if issue.status != "done":
            issue.status = "done"
            save_issue(project_dir, issue)
            result.issues_closed.append(issue_key)

    now = datetime.now(tz=timezone.utc)
    session.status = "done"
    session.updated_at = now
    if session.engagements:
        last = session.engagements[-1]
        if last.ended_at is None:
            last.ended_at = now
            last.outcome = "completed"
    save_session(project_dir, session)

    if not skip_worktree_cleanup:
        from tripwire.core.git_helpers import worktree_remove

        for wt in session.runtime_state.worktrees:
            try:
                worktree_remove(Path(wt.clone_path), Path(wt.worktree_path))
                result.worktrees_removed.append(wt.worktree_path)
            except (subprocess.SubprocessError, OSError):
                pass

    return result


def _verify_pr_merged(session) -> None:
    for wt in session.runtime_state.worktrees:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    wt.branch,
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
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    return
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            continue
    raise CompleteError(
        "complete/pr_not_merged",
        "No merged PR found for any session branch.",
    )


def _verify_review_ok(project_dir: Path, session) -> None:
    """Spec §11.2 step 4: most recent review exit_code must be ≤ 1.

    Reads ``sessions/<id>/review.json`` produced by ``session review``.
    Missing file means review never ran → refuse unless --force-review.
    """
    review_path = paths.session_dir(project_dir, session.id) / "review.json"
    if not review_path.is_file():
        raise CompleteError(
            "complete/no_review",
            f"No review.json for session {session.id!r} — run "
            f"`tripwire session review {session.id}` first, "
            f"or pass --force-review to bypass.",
        )
    try:
        data = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CompleteError(
            "complete/no_review",
            f"review.json for session {session.id!r} is unreadable: {exc}",
        ) from exc
    exit_code = data.get("exit_code")
    if not isinstance(exit_code, int):
        raise CompleteError(
            "complete/no_review",
            f"review.json for session {session.id!r} missing a valid exit_code.",
        )
    if exit_code > 1:
        verdict = data.get("verdict", "?")
        raise CompleteError(
            "complete/review_failed",
            f"Last review reported verdict={verdict!r} (exit_code={exit_code}). "
            f"Fix findings and re-review, or pass --force-review.",
        )


def _verify_issue_artifacts(project_dir: Path, session) -> None:
    try:
        manifest = load_issue_artifact_manifest(project_dir)
    except FileNotFoundError:
        return
    missing: list[str] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        for entry in manifest.artifacts:
            if not entry.required:
                continue
            if not status_at_or_past(
                issue.status, entry.required_at_status, project_dir
            ):
                continue
            file_path = paths.issue_dir(project_dir, issue_key) / entry.file
            if not file_path.is_file():
                missing.append(f"{issue_key}/{entry.file}")
    if missing:
        raise CompleteError(
            "complete/missing_artifacts",
            f"Missing required artifacts: {', '.join(missing)}",
        )


def _compute_node_diffs(project_dir: Path, session) -> list[dict]:
    """Stub: node reconciliation deferred to a later release.

    Returns an empty list in v0.7b — the PM reviews insights (per-session
    proposals) via `tripwire session insights` before calling complete.
    """
    return []
