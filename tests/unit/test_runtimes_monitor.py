"""Tests for the in-flight runtime monitor (v0.7.9 §A7).

Each tripwire (#9-#14) gets a focused test that hands a sequence of
parsed stream-json events to the monitor and asserts the emitted
``MonitorAction``s. The monitor is pure-function over events for
testability — the threaded log tail is tested separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from tripwire.runtimes.monitor import (
    InjectFollowUp,
    LogWarning,
    MonitorContext,
    RuntimeMonitor,
    SigtermProcess,
    TransitionStatus,
)


def _ctx(tmp_path: Path, **overrides) -> MonitorContext:
    pt = tmp_path / "pt"
    pt.mkdir(exist_ok=True)
    code = tmp_path / "code"
    code.mkdir(exist_ok=True)
    base = {
        "session_id": "s1",
        "pid": 1234,
        "log_path": tmp_path / "log.jsonl",
        "code_worktree": code,
        "pt_worktree": pt,
        "project_dir": tmp_path / "proj",
        "max_budget_usd": 10.0,
        "model_name": "claude-opus-4-7",
        "key_files": ["src/foo.py"],
        "required_artifacts": ["self-review.md"],
    }
    base.update(overrides)
    return MonitorContext(**base)


# ---------- Cost calc / tripwire #12 -------------------------------------


def test_cost_accumulates_from_assistant_usage(tmp_path):
    """Per-message usage events accumulate into cumulative_cost_usd.

    Single opus message: 1k input, 500 output → expected
    1k * $15/Mtok + 500 * $75/Mtok = $0.015 + $0.0375 = $0.0525.
    """
    monitor = RuntimeMonitor(_ctx(tmp_path))
    event = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {
                "input_tokens": 1000,
                "output_tokens": 500,
            },
        },
    }
    monitor.process_event(event)
    assert abs(monitor.cumulative_cost_usd - 0.0525) < 1e-9


def test_cost_includes_cache_tokens(tmp_path):
    """Cache write + cache read tokens add to the cost calculation."""
    monitor = RuntimeMonitor(_ctx(tmp_path))
    event = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 100,
                "cache_creation_input_tokens": 1000,
                "cache_read_input_tokens": 10000,
            },
        },
    }
    monitor.process_event(event)
    # 100*15 + 100*75 + 1000*18.75 + 10000*1.50 all per Mtok
    expected = (100 * 15.0 + 100 * 75.0 + 1000 * 18.75 + 10000 * 1.50) / 1_000_000
    assert abs(monitor.cumulative_cost_usd - expected) < 1e-9


def test_cost_overrun_emits_sigterm_pause_and_followup(tmp_path):
    """Tripwire #12 — the v075 fix.

    Cumulative cost crosses max_budget_usd → SIGTERM the subprocess +
    transition status to paused + inject PM follow-up. Three actions
    in that order.
    """
    monitor = RuntimeMonitor(_ctx(tmp_path, max_budget_usd=0.01))
    event = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        },
    }
    actions = monitor.process_event(event)
    kinds = [type(a).__name__ for a in actions]
    assert "SigtermProcess" in kinds
    assert "TransitionStatus" in kinds
    assert "InjectFollowUp" in kinds
    sigterm = next(a for a in actions if isinstance(a, SigtermProcess))
    assert sigterm.tripwire_id == "monitor/cost_overrun"
    assert sigterm.pid == 1234
    transition = next(a for a in actions if isinstance(a, TransitionStatus))
    assert transition.new_status == "paused"


def test_cost_overrun_only_fires_once(tmp_path):
    """Once budget is blown, subsequent events don't re-emit SIGTERM."""
    monitor = RuntimeMonitor(_ctx(tmp_path, max_budget_usd=0.01))
    event = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        },
    }
    monitor.process_event(event)  # fires
    second = monitor.process_event(event)  # already-fired, silent
    assert not any(isinstance(a, SigtermProcess) for a in second)


def test_cost_under_budget_no_action(tmp_path):
    """Below max_budget_usd, no actions emitted."""
    monitor = RuntimeMonitor(_ctx(tmp_path, max_budget_usd=10.0))
    event = {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "usage": {"input_tokens": 100, "output_tokens": 100},
        },
    }
    actions = monitor.process_event(event)
    assert actions == []


def test_unknown_model_uses_default_pricing(tmp_path):
    """Unrecognised model → falls back to default rate."""
    monitor = RuntimeMonitor(_ctx(tmp_path))
    event = {
        "type": "assistant",
        "message": {
            "model": "unknown-model-9001",
            "usage": {"input_tokens": 1000, "output_tokens": 1000},
        },
    }
    monitor.process_event(event)
    # default == opus rates
    expected = (1000 * 15.0 + 1000 * 75.0) / 1_000_000
    assert abs(monitor.cumulative_cost_usd - expected) < 1e-9


# ---------- Quota error / tripwire #13 -----------------------------------


def test_quota_error_transitions_to_failed(tmp_path):
    """Tripwire #13 — quota error in stream → auto-transition to failed."""
    monitor = RuntimeMonitor(_ctx(tmp_path))
    event = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "API Error: Quota exceeded for organization",
    }
    actions = monitor.process_event(event)
    transitions = [a for a in actions if isinstance(a, TransitionStatus)]
    assert len(transitions) == 1
    assert transitions[0].new_status == "failed"
    assert transitions[0].tripwire_id == "monitor/quota_error"


def test_normal_result_no_quota_action(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path))
    event = {
        "type": "result",
        "subtype": "success",
        "result": "Done.",
        "total_cost_usd": 0.05,
    }
    actions = monitor.process_event(event)
    assert not any(
        isinstance(a, TransitionStatus) and a.new_status == "failed" for a in actions
    )


# ---------- Failed-push loop / tripwire #14 ------------------------------


def test_failed_push_warning_at_5_consecutive(tmp_path):
    """5 consecutive failed `git push` attempts → log warning."""
    monitor = RuntimeMonitor(_ctx(tmp_path))
    fail = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "error: failed to push some refs to 'origin'",
                    "is_error": True,
                }
            ]
        },
    }
    push_call = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "git push origin feat/x"},
                }
            ]
        },
    }
    actions: list = []
    for _ in range(5):
        actions.extend(monitor.process_event(push_call))
        actions.extend(monitor.process_event(fail))
    warnings = [a for a in actions if isinstance(a, LogWarning)]
    sigterms = [a for a in actions if isinstance(a, SigtermProcess)]
    assert any("git push" in w.message.lower() for w in warnings)
    assert sigterms == []


def test_failed_push_sigterm_after_10_consecutive(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path))
    fail = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "error: failed to push some refs to 'origin'",
                    "is_error": True,
                }
            ]
        },
    }
    push_call = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "git push origin feat/x"},
                }
            ]
        },
    }
    actions: list = []
    for _ in range(11):
        actions.extend(monitor.process_event(push_call))
        actions.extend(monitor.process_event(fail))
    sigterms = [a for a in actions if isinstance(a, SigtermProcess)]
    assert len(sigterms) >= 1
    assert sigterms[0].tripwire_id == "monitor/push_loop"


def test_successful_push_resets_counter(tmp_path):
    """Successful push between failures resets the counter — no warning
    fires from a 5+5 split."""
    monitor = RuntimeMonitor(_ctx(tmp_path))
    push_call = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "git push origin feat/x"},
                }
            ]
        },
    }
    fail = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "error: failed to push",
                    "is_error": True,
                }
            ]
        },
    }
    success = {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "t1",
                    "content": "Branch 'feat/x' set up to track 'origin/feat/x'.",
                }
            ]
        },
    }
    actions: list = []
    for _ in range(4):
        actions.extend(monitor.process_event(push_call))
        actions.extend(monitor.process_event(fail))
    actions.extend(monitor.process_event(push_call))
    actions.extend(monitor.process_event(success))
    for _ in range(4):
        actions.extend(monitor.process_event(push_call))
        actions.extend(monitor.process_event(fail))
    assert not any(isinstance(a, LogWarning) for a in actions)


# ---------- Code-PR-without-PT-branch / tripwire #10 ---------------------


def test_pr_create_with_empty_pt_branch_emits_inject(tmp_path):
    """`gh pr create` from code worktree but PT worktree has no commits
    beyond main → inject reminder."""
    tmp_path / "pt"
    tmp_path / "code"
    monitor = RuntimeMonitor(_ctx(tmp_path))
    pr_create = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {
                        "command": (
                            "gh pr create --repo SeidoAI/code "
                            "--base main --head feat/x --title 'feat: x' "
                            "--body 'desc'"
                        ),
                    },
                }
            ]
        },
    }
    with patch("tripwire.runtimes.monitor._pt_branch_has_commits", return_value=False):
        actions = monitor.process_event(pr_create)
    injects = [a for a in actions if isinstance(a, InjectFollowUp)]
    assert injects
    assert injects[0].tripwire_id == "monitor/code_pr_no_pt"


def test_pr_create_with_populated_pt_branch_no_action(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path))
    pr_create = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "gh pr create --repo SeidoAI/code --title x"},
                }
            ]
        },
    }
    with patch("tripwire.runtimes.monitor._pt_branch_has_commits", return_value=True):
        actions = monitor.process_event(pr_create)
    assert not any(isinstance(a, InjectFollowUp) for a in actions)


# ---------- Session-complete-without-artifacts / tripwire #9 -------------


def test_session_complete_text_with_missing_artifacts_emits_inject(tmp_path):
    """Process-exit hook: agent's final text says 'session complete' but
    self-review.md not committed → inject follow-up."""
    monitor = RuntimeMonitor(_ctx(tmp_path, required_artifacts=["self-review.md"]))
    final_msg = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "All done. Session complete."}]
        },
    }
    monitor.process_event(final_msg)
    with patch(
        "tripwire.runtimes.monitor._committed_paths_in_branch",
        return_value=set(),
    ):
        actions = monitor.on_process_exit(exit_code=0)
    injects = [a for a in actions if isinstance(a, InjectFollowUp)]
    assert injects
    assert injects[0].tripwire_id == "monitor/session_complete_no_artifacts"
    assert "self-review.md" in injects[0].message


def test_session_complete_with_artifacts_no_action(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path, required_artifacts=["self-review.md"]))
    final = {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Session complete."}]},
    }
    monitor.process_event(final)
    with patch(
        "tripwire.runtimes.monitor._committed_paths_in_branch",
        return_value={"sessions/s1/self-review.md"},
    ):
        actions = monitor.on_process_exit(exit_code=0)
    assert not any(
        isinstance(a, InjectFollowUp)
        and a.tripwire_id == "monitor/session_complete_no_artifacts"
        for a in actions
    )


def test_no_session_complete_no_action(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path, required_artifacts=["self-review.md"]))
    final = {
        "type": "assistant",
        "message": {
            "content": [{"type": "text", "text": "Stopped to ask: which API?"}]
        },
    }
    monitor.process_event(final)
    actions = monitor.on_process_exit(exit_code=0)
    assert not any(
        isinstance(a, InjectFollowUp)
        and a.tripwire_id == "monitor/session_complete_no_artifacts"
        for a in actions
    )


# ---------- Commit divergence / tripwire #11 -----------------------------


def test_commits_outside_key_files_emit_warning(tmp_path):
    """Files committed to the code worktree branch that aren't in
    session.key_files → log warning (no block)."""
    monitor = RuntimeMonitor(_ctx(tmp_path, key_files=["src/foo.py", "src/bar.py"]))
    with patch(
        "tripwire.runtimes.monitor._commits_diff_files",
        return_value={"src/foo.py", "src/wandered_off.py"},
    ):
        actions = monitor.on_process_exit(exit_code=0)
    warnings = [
        a
        for a in actions
        if isinstance(a, LogWarning) and a.tripwire_id == "monitor/key_files_drift"
    ]
    assert warnings
    assert "src/wandered_off.py" in warnings[0].message
    # Drift is warn-only — no SIGTERM, no transition.
    assert not any(isinstance(a, SigtermProcess) for a in actions)


def test_commits_within_key_files_no_warning(tmp_path):
    monitor = RuntimeMonitor(_ctx(tmp_path, key_files=["src/foo.py", "src/bar.py"]))
    with patch(
        "tripwire.runtimes.monitor._commits_diff_files",
        return_value={"src/foo.py", "src/bar.py"},
    ):
        actions = monitor.on_process_exit(exit_code=0)
    assert not any(
        isinstance(a, LogWarning) and a.tripwire_id == "monitor/key_files_drift"
        for a in actions
    )


# ---------- Threaded log tail --------------------------------------------


def test_monitor_thread_tails_log_and_processes_each_line(tmp_path):
    """End-to-end: write JSONL to a log file; the thread parses each
    line and the action sink sees the resulting actions."""
    from tripwire.runtimes.monitor import MonitorThread

    log = tmp_path / "tail.jsonl"
    log.write_text("")  # exists, empty
    monitor = RuntimeMonitor(_ctx(tmp_path, log_path=log, max_budget_usd=0.0001))
    sink: list = []
    thread = MonitorThread(monitor, sink.append, poll_interval=0.05)
    thread.start()
    try:
        with log.open("a") as f:
            f.write(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "model": "claude-opus-4-7",
                            "usage": {
                                "input_tokens": 1000,
                                "output_tokens": 1000,
                            },
                        },
                    }
                )
                + "\n"
            )
            f.flush()
        # Wait up to 2s for the thread to pick the line up.
        import time

        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and not sink:
            time.sleep(0.05)
    finally:
        thread.stop()
    assert any(isinstance(a, SigtermProcess) for a in sink)


def test_monitor_thread_skips_malformed_lines(tmp_path):
    """A malformed line doesn't crash the thread — it logs and moves on."""
    from tripwire.runtimes.monitor import MonitorThread

    log = tmp_path / "tail.jsonl"
    log.write_text("not json\n")
    monitor = RuntimeMonitor(_ctx(tmp_path, log_path=log))
    sink: list = []
    thread = MonitorThread(monitor, sink.append, poll_interval=0.05)
    thread.start()
    try:
        import time

        time.sleep(0.2)
    finally:
        thread.stop()
    # Did not raise.
