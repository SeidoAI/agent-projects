"""Tests for the post-PR auto-check watcher (v0.7.9 §A8).

The watcher polls open PRs across active sessions and emits actions
when one of three tripwires fires:

  #15  code PR open but PT PR doesn't exist after 10 min
  #17  PR merged but session.status still ``executing``
  #18-19  PT PR open but missing required artifacts

The :class:`PRWatcher` is pure-function over its inputs — the
caller injects a ``fetch_pr`` and ``fetch_pr_files`` callable so
tests can supply canned GitHub responses.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from tripwire.core.pr_watcher import (
    CommentOnPR,
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
        "pt_repo": "ExampleOrg/example-project",
        "pt_branch": "proj/s1",
        "pt_pr_number": None,
        "required_artifacts": [
            "sessions/s1/self-review.md",
            "sessions/s1/insights.yaml",
        ],
        "session_status": "executing",
    }
    base.update(kw)
    return WatchedSession(**base)


def _state(**kw) -> PRState:
    base = {"number": 42, "state": "open", "merged": False, "head_branch": "feat/s1"}
    base.update(kw)
    return PRState(**base)


# ---------- Tripwire #15 — code PR no PT PR after 10 min -----------------


def test_code_pr_open_no_pt_after_10min_emits_inject_and_reengage():
    ws = _ws(pt_pr_number=None)
    now = ws.code_pr_opened_at + timedelta(minutes=11)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    kinds = [type(a).__name__ for a in actions]
    assert "InjectFollowUp" in kinds
    assert "ReengageAgent" in kinds
    inject = next(a for a in actions if isinstance(a, InjectFollowUp))
    assert inject.tripwire_id == "watcher/code_pr_no_pt_pr"
    assert inject.session_id == "s1"


def test_code_pr_open_pt_pr_exists_no_action():
    ws = _ws(pt_pr_number=99)
    now = ws.code_pr_opened_at + timedelta(minutes=20)

    def fetch_pr(repo, pr_number, token=None):
        if pr_number == 42:
            return _state(state="open", merged=False)
        return _state(number=99, state="open", merged=False, head_branch="proj/s1")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        isinstance(a, InjectFollowUp) and a.tripwire_id == "watcher/code_pr_no_pt_pr"
        for a in actions
    )


def test_code_pr_open_under_10min_no_action():
    ws = _ws(pt_pr_number=None)
    now = ws.code_pr_opened_at + timedelta(minutes=5)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert actions == []


def test_code_pr_no_pt_fires_only_once_per_session():
    """A second tick with the same condition does not re-emit."""
    ws = _ws(pt_pr_number=None)
    now = ws.code_pr_opened_at + timedelta(minutes=11)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    first = watcher.tick([ws], now=now)
    second = watcher.tick([ws], now=now + timedelta(minutes=5))
    assert any(isinstance(a, InjectFollowUp) for a in first)
    assert not any(isinstance(a, InjectFollowUp) for a in second)


# ---------- Tripwire #17 — PR merged but status executing ----------------


def test_pr_merged_but_executing_emits_transition_and_followup():
    ws = _ws(session_status="executing", pt_pr_number=99)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        if pr_number == 42:
            return _state(state="closed", merged=True)
        return _state(number=99, state="open", merged=False, head_branch="proj/s1")

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    transitions = [
        a
        for a in actions
        if isinstance(a, TransitionStatus)
        and a.tripwire_id == "watcher/merged_executing"
    ]
    assert len(transitions) == 1
    assert transitions[0].new_status == "paused"
    injects = [
        a
        for a in actions
        if isinstance(a, InjectFollowUp) and a.tripwire_id == "watcher/merged_executing"
    ]
    assert len(injects) == 1


def test_pr_merged_status_not_executing_no_action():
    ws = _ws(session_status="paused", pt_pr_number=99)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="closed", merged=True)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        isinstance(a, TransitionStatus) and a.tripwire_id == "watcher/merged_executing"
        for a in actions
    )


# ---------- Tripwires #18-19 — PT PR missing artifacts -------------------


def test_pt_pr_missing_artifact_emits_comment_and_reengage():
    ws = _ws(pt_pr_number=99)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        if pr_number == 42:
            return _state(state="open", merged=False)
        return _state(number=99, state="open", merged=False, head_branch="proj/s1")

    def fetch_pr_files(repo, pr_number, token=None):
        if pr_number == 99:
            return [{"filename": "sessions/s1/self-review.md"}]
        return []

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=fetch_pr_files)
    actions = watcher.tick([ws], now=now)
    comments = [
        a
        for a in actions
        if isinstance(a, CommentOnPR)
        and a.tripwire_id == "watcher/pt_pr_missing_artifacts"
    ]
    assert len(comments) == 1
    assert "sessions/s1/insights.yaml" in comments[0].body
    assert comments[0].pr_number == 99
    assert comments[0].repo == "ExampleOrg/example-project"
    assert any(isinstance(a, ReengageAgent) for a in actions)


def test_pt_pr_complete_artifacts_no_action():
    ws = _ws(pt_pr_number=99)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False)

    def fetch_pr_files(repo, pr_number, token=None):
        if pr_number == 99:
            return [
                {"filename": "sessions/s1/self-review.md"},
                {"filename": "sessions/s1/insights.yaml"},
            ]
        return []

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=fetch_pr_files)
    actions = watcher.tick([ws], now=now)
    assert not any(
        isinstance(a, CommentOnPR)
        and a.tripwire_id == "watcher/pt_pr_missing_artifacts"
        for a in actions
    )


def test_pt_pr_missing_artifact_fires_once_per_pr():
    ws = _ws(pt_pr_number=99)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        return _state(state="open", merged=False)

    def fetch_pr_files(repo, pr_number, token=None):
        return [{"filename": "sessions/s1/self-review.md"}]

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=fetch_pr_files)
    first = watcher.tick([ws], now=now)
    second = watcher.tick([ws], now=now + timedelta(minutes=5))
    assert any(isinstance(a, CommentOnPR) for a in first)
    assert not any(isinstance(a, CommentOnPR) for a in second)


# ---------- Failure modes / robustness -----------------------------------


def test_fetch_failure_yields_no_actions_for_that_session():
    """A network failure on one session must not crash the whole tick."""
    ws_a = _ws(session_id="s_ok", pt_pr_number=99)
    ws_b = _ws(session_id="s_bad", code_pr_number=77, pt_pr_number=None)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)

    def fetch_pr(repo, pr_number, token=None):
        if pr_number == 77:
            raise RuntimeError("connection reset")
        return _state(state="open", merged=False)

    watcher = PRWatcher(fetch_pr=fetch_pr, fetch_pr_files=_no_files)
    actions = watcher.tick([ws_a, ws_b], now=now)
    # Did not raise. ws_b's actions are silently skipped; ws_a still
    # gets evaluated.
    sessions_with_actions = {
        getattr(a, "session_id", None) for a in actions if hasattr(a, "session_id")
    }
    assert "s_bad" not in sessions_with_actions


def test_session_with_no_code_pr_skipped():
    ws = _ws(code_pr_number=None, code_pr_opened_at=None)
    now = datetime(2026, 4, 25, 13, 0, tzinfo=timezone.utc)
    watcher = PRWatcher(fetch_pr=_panic_fetch, fetch_pr_files=_no_files)
    actions = watcher.tick([ws], now=now)
    assert actions == []


# ---------- helpers -------------------------------------------------------


def _no_files(repo, pr_number, token=None):
    return []


def _panic_fetch(
    repo, pr_number, token=None
):  # pragma: no cover — should never be called
    raise AssertionError("fetch_pr should not have been called")
