"""Session complete orchestration.

Gates session close-out behind: (a) session in a completable status,
(b) every worktree branch has a merged PR, (c) every required issue
artifact present, (d) most recent review exit_code ≤ 1. Then transitions
the session to `completed` via the workflow executor.

v0.7.9 §A4: every gate is mandatory. There are no bypass flags. A
session that can't pass these gates should be `tripwire session
abandon`-ed, which is a terminal status that does not claim success.

v0.13 (KUI-…): the inline side-effects (flip drafts, sweep issues,
remove worktrees, append telemetry, close engagement) have moved out:

- ``flip_drafts_to_ready`` → Layer-1 CLI ``tripwire session flip-drafts-ready``
  (chained from ``tripwire session prepare-for-completion``).
- ``sweep_issues`` → Layer-1 ``tripwire session sweep-issues-forward``.
- ``remove_worktrees`` → Layer-1 ``tripwire session remove-worktrees``.
- ``append_telemetry_row`` → executor post-write hook
  (:func:`tripwire.core.workflow.side_effects.append_telemetry_record`).
- ``close_active_engagement`` → executor post-write hook.

This helper now: verifies gates, then calls ``execute_transition``
which is the sole writer of ``session.status``.

Insights application is out-of-scope here — the PM's
`/pm-session-complete` runs `tripwire session insights apply/reject`
before invoking this routine.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.core import paths
from tripwire.core.issue_artifact_store import (
    load_issue_artifact_manifest,
    status_at_or_past,
)
from tripwire.core.session_store import load_session
from tripwire.core.store import load_issue


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
) -> CompleteResult:
    """Run the close-out gates then transition the session to `completed`.

    Gates per spec §11.2 (v0.7.9 §A4: no bypass flags):
      1. Status in {in_review, verified}.
      2. Every worktree branch has a merged PR.
      3. Per-issue required artifacts present.
      4. Most recent review exit_code ≤ 1.

    If a session can't pass these gates, the right move is
    ``tripwire session abandon`` (terminal status that does not claim
    success), not a bypass flag.

    v0.13: the status flip routes through
    :func:`tripwire.core.workflow.transitions.execute_transition` (sole
    writer of ``session.status``). Inline side-effects (flip drafts,
    sweep issues, worktree cleanup, telemetry, engagement close) have
    moved out — the executor handles the housekeeping hooks and the
    agent procedure invokes the Layer-1 CLI wrappers before/after this
    helper.
    """
    session = load_session(project_dir, session_id)
    result = CompleteResult(session_id=session_id)

    # Spec §11.2 step 1 — narrow status gate. `in_progress`, `executing`,
    # `active` must go through /pm-session-review first.
    completable = {"in_review", "verified"}
    if session.status not in completable:
        raise CompleteError(
            "complete/not_active",
            f"Session status is {session.status!r}; expected one of "
            f"{sorted(completable)}. Run /pm-session-review first. "
            "If the session can't legitimately reach `done`, run "
            "`tripwire session abandon` instead.",
        )

    _verify_pr_merged(session)
    _verify_issue_artifacts(project_dir, session)
    _verify_review_ok(project_dir, session)

    result.node_diffs = _compute_node_diffs(project_dir, session)

    if dry_run:
        return result

    # v0.13: route the status flip through the workflow executor — the
    # sole writer of ``session.status``. Engagement close + telemetry +
    # audit are post-write hooks fired inside ``execute_transition``.
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    try:
        transition = execute_transition(
            project_dir,
            workflow_id="coding-session",
            instance_id=session_id,
            target_status="completed",
            flags={"action": "session_complete"},
        )
    except TransitionError as exc:
        raise CompleteError(
            "complete/transition_error", f"executor refused: {exc}"
        ) from exc
    if not transition.ok:
        raise CompleteError(
            "complete/transition_rejected",
            f"transition to completed rejected: "
            f"{transition.message or transition.reason}",
        )

    return result


def _flip_drafts_to_ready(session) -> None:
    """Flip every session-start draft PR to ready (v0.7.5 item A).

    For each worktree with a recorded ``draft_pr_url``, run ``gh pr
    ready <url>`` from inside that worktree. Idempotent: ``gh pr
    ready`` on an already-ready or merged PR is harmless and we
    intentionally pass ``check=False`` so a noisy "PR is not draft"
    warning doesn't fail the whole complete.

    Worktrees without a ``draft_pr_url`` (in-flight sessions that
    started before v0.7.5 landed and still lack the recorded URL) fall
    back to ``gh pr create --fill`` so a PR exists to merge against.
    The fallback is best-effort — if the agent's exit protocol already
    opened the PR, gh errors with "a PR already exists" which we swallow.
    """
    for wt in session.runtime_state.worktrees:
        if wt.draft_pr_url:
            subprocess.run(
                ["gh", "pr", "ready", wt.draft_pr_url],
                cwd=wt.worktree_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        else:
            subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--head",
                    wt.branch,
                    "--fill",
                ],
                cwd=wt.worktree_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )


def _verify_pr_merged(session) -> None:
    """Require every worktree branch to have a merged PR; raise
    :class:`CompleteError` naming the unmerged branch(es) otherwise.
    ``gh`` is invoked from inside each worktree so it picks up the
    correct remote when worktrees have different origins.
    """
    worktrees = list(session.runtime_state.worktrees)
    if not worktrees:
        raise CompleteError(
            "complete/pr_not_merged",
            "Session has no recorded worktrees; cannot verify any PR merged.",
        )
    unmerged: list[str] = []
    for wt in worktrees:
        merged = False
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
                cwd=wt.worktree_path,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    merged = True
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            # Treat "gh errored / timed out / returned garbage" as "not
            # merged" — conservative: operator re-runs once the
            # environment is healthy, or `tripwire session abandon` if
            # the session genuinely shouldn't ship.
            pass
        if not merged:
            unmerged.append(wt.branch)
    if unmerged:
        raise CompleteError(
            "complete/pr_not_merged",
            f"No merged PR found for branch(es): {', '.join(unmerged)}",
        )


def _verify_review_ok(project_dir: Path, session) -> None:
    """Spec §11.2 step 4: most recent review exit_code must be ≤ 1.

    Reads ``sessions/<id>/review.json`` produced by ``session review``.
    Missing file means review never ran → refuse. The session needs to
    actually go through review before claiming done.
    """
    review_path = paths.session_dir(project_dir, session.id) / "review.json"
    if not review_path.is_file():
        raise CompleteError(
            "complete/no_review",
            f"No review.json for session {session.id!r} — run "
            f"`tripwire session review {session.id}` first.",
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
            f"Fix findings and re-review.",
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
