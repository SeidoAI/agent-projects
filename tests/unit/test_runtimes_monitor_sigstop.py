"""v0.7.10 §3.B4 — pause-on-CI-wait (SIGSTOP/SIGCONT during CI-wait).

When the agent enters its CI-wait loop after PR-open (per §3.B1), it
either calls `gh pr checks <num> --watch` (single blocking poll) or a
`sleep 30; gh pr view <num> --json statusCheckRollup` polling loop. In
both cases the agent is functionally idle but burns API tokens on each
turn. The runtime monitor detects this state from the stream-json log
and SIGSTOPs the agent process so token-burn drops to ~0 during the
wait.

Resume is bounded by a defensive 30-min SIGCONT — even if external
state never wakes the agent, it can't be left frozen indefinitely.
The 2026-04-25 batch had ~10 min of cumulative CI-wait across six
sessions; pausing during that window is what saves the tokens.

Tests cover three slices:
  - Monitor detection: tool_use commands matching either pattern emit
    a `SuspendProcess` action, deduped per suspend-cycle.
  - Process primitives: `send_sigstop` / `send_sigcont` thin wrappers
    in `process_helpers.py`.
  - Executor handler: `SuspendProcess` action triggers `send_sigstop`
    on the pid and schedules a defensive 30-min SIGCONT.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from tripwire.runtimes.monitor import (
    MonitorContext,
    ResumeProcess,
    RuntimeMonitor,
    SuspendProcess,
)
from tripwire.runtimes.monitor_actions import ActionExecutor


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
    }
    base.update(overrides)
    return MonitorContext(**base)


def _bash(cmd: str, *, tool_use_id: str = "tu-1") -> dict:
    """Build an `assistant` event whose only content is a Bash tool_use."""
    return {
        "type": "assistant",
        "message": {
            "model": "claude-opus-4-7",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_use_id,
                    "name": "Bash",
                    "input": {"command": cmd},
                }
            ],
        },
    }


# ---------- Monitor detection -------------------------------------------


class TestSuspendDetection:
    def test_gh_pr_checks_watch_emits_suspend(self, tmp_path):
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr checks 42 --watch"))
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert len(suspends) == 1
        assert suspends[0].pid == 1234
        assert suspends[0].tripwire_id == "monitor/ci_wait_suspend"

    def test_gh_pr_view_status_check_rollup_emits_suspend(self, tmp_path):
        """The polling-loop variant: `gh pr view <num> --json statusCheckRollup`."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(
            _bash("gh pr view 42 --json statusCheckRollup")
        )
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert len(suspends) == 1

    def test_unrelated_bash_does_not_emit_suspend(self, tmp_path):
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("git push origin feat/x"))
        assert not any(isinstance(a, SuspendProcess) for a in actions)

    def test_gh_pr_view_without_status_check_does_not_emit_suspend(self, tmp_path):
        """`gh pr view --json title` is not a CI-wait — only the
        statusCheckRollup variant counts."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr view 42 --json title"))
        assert not any(isinstance(a, SuspendProcess) for a in actions)

    def test_idempotent_does_not_re_emit_while_suspended(self, tmp_path):
        """A second CI-poll while still suspended must not re-fire suspend.
        Without this, every poll iteration in the agent's loop would
        re-suspend a process that's already frozen — wasteful but more
        importantly, races against the resume side."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        first = monitor.process_event(_bash("gh pr checks 42 --watch", tool_use_id="t1"))
        second = monitor.process_event(
            _bash("gh pr checks 42 --watch", tool_use_id="t2")
        )
        assert any(isinstance(a, SuspendProcess) for a in first)
        assert not any(isinstance(a, SuspendProcess) for a in second)


# ---------- Process primitives ------------------------------------------


class TestSigstopSigcontPrimitives:
    def test_send_sigstop_calls_os_kill_with_sigstop(self):
        from tripwire.core.process_helpers import send_sigstop

        with patch("tripwire.core.process_helpers.os.kill") as mock_kill:
            ok = send_sigstop(4242)

        import signal as _signal

        assert ok is True
        mock_kill.assert_called_once_with(4242, _signal.SIGSTOP)

    def test_send_sigcont_calls_os_kill_with_sigcont(self):
        from tripwire.core.process_helpers import send_sigcont

        with patch("tripwire.core.process_helpers.os.kill") as mock_kill:
            ok = send_sigcont(4242)

        import signal as _signal

        assert ok is True
        mock_kill.assert_called_once_with(4242, _signal.SIGCONT)

    def test_send_sigstop_returns_false_on_missing_pid(self):
        from tripwire.core.process_helpers import send_sigstop

        with patch(
            "tripwire.core.process_helpers.os.kill",
            side_effect=ProcessLookupError(),
        ):
            assert send_sigstop(999_999) is False

    def test_send_sigcont_returns_false_on_missing_pid(self):
        from tripwire.core.process_helpers import send_sigcont

        with patch(
            "tripwire.core.process_helpers.os.kill",
            side_effect=ProcessLookupError(),
        ):
            assert send_sigcont(999_999) is False


# ---------- Executor handler --------------------------------------------


@pytest.fixture
def tmp_project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True)
    return tmp_path


class TestSuspendExecutor:
    def test_execute_suspend_sends_sigstop(self, tmp_project: Path):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        with (
            patch("tripwire.runtimes.monitor_actions.send_sigstop") as mock_stop,
            patch("tripwire.runtimes.monitor_actions.threading.Timer") as mock_timer,
        ):
            executor.execute(
                SuspendProcess(
                    tripwire_id="monitor/ci_wait_suspend",
                    pid=4242,
                    reason="agent in CI-wait via gh pr checks --watch",
                )
            )
        mock_stop.assert_called_once_with(4242)
        # The defensive timer is scheduled.
        assert mock_timer.called
        timer_args = mock_timer.call_args
        # 30 min = 1800s defensive cap.
        assert timer_args.args[0] == 30 * 60

    def test_execute_resume_sends_sigcont(self, tmp_project: Path):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        with patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont:
            executor.execute(
                ResumeProcess(
                    tripwire_id="monitor/ci_wait_resume",
                    pid=4242,
                    reason="defensive 30-min cap",
                )
            )
        mock_cont.assert_called_once_with(4242)
