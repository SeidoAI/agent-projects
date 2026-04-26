"""v0.7.10 §3.B2 — auto-PM-followup on post-merge CI failure.

When a session's code PR has been merged but CI on the merge commit
later goes red (a regression), and the session has already exited
(``status in {paused, in_review, verified, completed, done}``), the
runtime watcher detects it and:

  1. Injects a ``## PM follow-up — post-merge CI failure (auto-injected)``
     block into the canonical main-PT plan.md.
  2. Transitions the session to ``paused``.
  3. Re-engages the agent (pause + ``spawn --resume``).

Without this, the 2026-04-25 batch had three sessions where PMs had to
manually run ``tripwire session pause`` + edit plan.md + ``spawn
--resume`` — three times for v075 alone.

These tests assert the watcher's policy slice. The fetcher impl that
populates ``PRState.check_status`` from the GitHub commits/check-runs
API is exercised by the integration tier.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.pr_watcher import (
    InjectFollowUp,
    PRState,
    PRWatcher,
    ReengageAgent,
    TransitionStatus,
    WatchedSession,
)


def _ws(**kw) -> WatchedSession:
    base = {
        "session_id": "s1",
        "project_dir": Path("/tmp/proj"),
        "code_repo": "SeidoAI/code",
        "code_branch": "feat/s1",
        "code_pr_number": 42,
        "code_pr_opened_at": datetime(2026, 4, 25, 12, 0, tzinfo=timezone.utc),
        "pt_repo": "SeidoAI/tripwire-v0",
        "pt_branch": "proj/s1",
        "pt_pr_number": 99,
        "required_artifacts": [],
        "session_status": "done",
    }
    base.update(kw)
    return WatchedSession(**base)


def _state(**kw) -> PRState:
    base = {
        "number": 42,
        "state": "closed",
        "merged": True,
        "head_branch": "feat/s1",
        "check_status": "FAIL",
    }
    base.update(kw)
    return PRState(**base)


def _no_files(repo, pr_number, token=None):
    return []


# ---------- Fires when post-merge CI red on inactive session -------------


def test_post_merge_ci_failure_on_done_session_emits_inject_pause_reengage():
    ws = _ws(session_status="done")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        if pr_number == 42:
            return _state(merged=True, check_status="FAIL")
        return _state(number=99, state="open", merged=False, check_status=None)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)

    injects = [
        a
        for a in actions
        if isinstance(a, InjectFollowUp)
        and a.tripwire_id == "watcher/post_merge_ci_failure"
    ]
    transitions = [
        a
        for a in actions
        if isinstance(a, TransitionStatus)
        and a.tripwire_id == "watcher/post_merge_ci_failure"
    ]
    reengages = [
        a
        for a in actions
        if isinstance(a, ReengageAgent) and a.reason == "watcher/post_merge_ci_failure"
    ]
    assert len(injects) == 1, "post-merge CI failure must inject a follow-up"
    assert "post-merge CI failure" in injects[0].message
    assert len(transitions) == 1
    assert transitions[0].new_status == "paused"
    assert len(reengages) == 1


def test_post_merge_ci_failure_on_in_review_session_fires():
    """The session may still be in_review if a recent merge regressed
    on top of an unmerged PR — same handling applies."""
    ws = _ws(session_status="in_review")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(check_status="FAIL")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert any(
        isinstance(a, InjectFollowUp)
        and a.tripwire_id == "watcher/post_merge_ci_failure"
        for a in actions
    )


# ---------- Does NOT fire ------------------------------------------------


def test_no_action_when_session_still_executing():
    """An executing session with a red CI is the in-flight monitor's
    problem (#9 / B1's responsibility) — not the post-merge tripwire's."""
    ws = _ws(session_status="executing")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(check_status="FAIL")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        getattr(a, "tripwire_id", None) == "watcher/post_merge_ci_failure"
        or getattr(a, "reason", None) == "watcher/post_merge_ci_failure"
        for a in actions
    )


def test_no_action_when_check_status_pass():
    ws = _ws(session_status="done")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(check_status="PASS")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        getattr(a, "tripwire_id", None) == "watcher/post_merge_ci_failure"
        for a in actions
    )


def test_no_action_when_pr_not_merged():
    """An unmerged PR with red CI is the in-flight CI-aware-exit's job."""
    ws = _ws(session_status="done")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False, check_status="FAIL")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        getattr(a, "tripwire_id", None) == "watcher/post_merge_ci_failure"
        for a in actions
    )


def test_no_action_when_check_status_unknown():
    """A check_status of None means we don't know — don't fire on
    ambiguity. The fetcher returns None when the API response had no
    runs (e.g. CI never ran yet)."""
    ws = _ws(session_status="done")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(check_status=None)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        getattr(a, "tripwire_id", None) == "watcher/post_merge_ci_failure"
        for a in actions
    )


# ---------- Idempotency --------------------------------------------------


def test_fires_only_once_per_session():
    """A second tick with the same condition must not re-emit. The
    plan calls this out explicitly: 'idempotent — if the auto-injected
    block already exists, no-op.'"""
    ws = _ws(session_status="done")
    now = datetime(2026, 4, 26, 10, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(check_status="FAIL")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    first = watcher.tick([ws], now=now)
    second = watcher.tick(
        [ws],
        now=now.replace(minute=now.minute + 5),
    )
    assert any(
        isinstance(a, InjectFollowUp)
        and a.tripwire_id == "watcher/post_merge_ci_failure"
        for a in first
    )
    assert not any(
        isinstance(a, InjectFollowUp)
        and a.tripwire_id == "watcher/post_merge_ci_failure"
        for a in second
    )
