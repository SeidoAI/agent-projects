"""v0.7.10 §3.B4 — pause-on-CI-wait (SIGSTOP/SIGCONT during CI-wait).

When the agent enters its CI-wait loop after PR-open (per §3.B1), it
either calls `gh pr checks <num> --watch` (single blocking poll) or a
`sleep 30; gh pr view <num> --json statusCheckRollup` polling loop. In
both cases the agent is functionally idle but burns API tokens on each
turn. The runtime monitor detects this state from the stream-json log
and SIGSTOPs the agent process so token-burn drops to ~0 during the
wait.

Resume is driven by a GH-polling background thread (B4b) that calls
``gh pr view <num> --json statusCheckRollup`` every 30s and SIGCONTs
the agent the moment all checks have a non-pending conclusion. A
defensive 30-min ``threading.Timer`` SIGCONT remains as a backstop
in case the poll thread dies or the PR number can't be extracted
from the original tool_use command.

Tests cover four slices:
  - Monitor detection: tool_use commands matching either pattern emit
    a `SuspendProcess` action carrying the PR number + code_worktree,
    deduped per suspend-cycle.
  - Process primitives: `send_sigstop` / `send_sigcont` thin wrappers
    in `process_helpers.py`.
  - Executor suspend handler: `SuspendProcess` action triggers
    `send_sigstop`, schedules the defensive 30-min SIGCONT timer,
    and starts the GH-polling resume thread when a PR number is
    available.
  - GH-polling resume (B4b): `_gh_poll_once` SIGCONTs when all checks
    are completed, no-ops while pending, and coordinates with the
    defensive timer via a shared ``threading.Event`` so SIGCONT only
    fires once per suspension.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_suspend_carries_pr_number_from_gh_pr_checks(self, tmp_path):
        """B4b — the poller needs the PR number to call `gh pr view`."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr checks 42 --watch"))
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert suspends[0].pr_number == 42

    def test_suspend_carries_pr_number_from_gh_pr_view(self, tmp_path):
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr view 99 --json statusCheckRollup"))
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert suspends[0].pr_number == 99

    def test_suspend_carries_code_worktree(self, tmp_path):
        """B4b — the poller runs `gh` from the agent's code worktree
        so it inherits the right git remote without needing --repo."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr checks 42 --watch"))
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert suspends[0].code_worktree == (tmp_path / "code")

    def test_suspend_with_unparseable_pr_number_still_fires(self, tmp_path):
        """If the bash command is a CI-poll but the PR number is
        unrecognisable (e.g. shell variable), still SIGSTOP — the
        defensive 30-min timer is the fallback."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr checks --watch"))
        suspends = [a for a in actions if isinstance(a, SuspendProcess)]
        assert len(suspends) == 1
        assert suspends[0].pr_number is None

    def test_gh_pr_view_status_check_rollup_emits_suspend(self, tmp_path):
        """The polling-loop variant: `gh pr view <num> --json statusCheckRollup`."""
        monitor = RuntimeMonitor(_ctx(tmp_path))
        actions = monitor.process_event(_bash("gh pr view 42 --json statusCheckRollup"))
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
        first = monitor.process_event(
            _bash("gh pr checks 42 --watch", tool_use_id="t1")
        )
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

    def test_suspend_with_pr_context_starts_poll_thread(self, tmp_project: Path):
        """B4b — when SuspendProcess carries pr_number + code_worktree,
        a daemon thread is started to poll `gh pr view` for CI
        completion. The defensive timer still gets scheduled too."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        with (
            patch("tripwire.runtimes.monitor_actions.send_sigstop"),
            patch("tripwire.runtimes.monitor_actions.threading.Timer"),
            patch("tripwire.runtimes.monitor_actions.threading.Thread") as mock_thread,
        ):
            executor.execute(
                SuspendProcess(
                    tripwire_id="monitor/ci_wait_suspend",
                    pid=4242,
                    reason="...",
                    pr_number=42,
                    code_worktree=Path("/tmp/wt"),
                )
            )
        assert mock_thread.called
        thread_inst = mock_thread.return_value
        thread_inst.start.assert_called_once()
        # Daemon flag prevents the poll thread from blocking shutdown.
        assert mock_thread.call_args.kwargs.get("daemon") is True

    def test_suspend_without_pr_context_skips_poll_thread(self, tmp_project: Path):
        """If the PR number couldn't be parsed, only the defensive
        timer guards the suspension. No poll thread is started."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        with (
            patch("tripwire.runtimes.monitor_actions.send_sigstop"),
            patch("tripwire.runtimes.monitor_actions.threading.Timer"),
            patch("tripwire.runtimes.monitor_actions.threading.Thread") as mock_thread,
        ):
            executor.execute(
                SuspendProcess(
                    tripwire_id="monitor/ci_wait_suspend",
                    pid=4242,
                    reason="...",
                    pr_number=None,
                    code_worktree=None,
                )
            )
        # Thread must not have been instantiated for the polling path.
        assert not mock_thread.called


# ---------- B4b: GH-polling resume ----------------------------------------


class TestB4bGhPollResume:
    """Single-iteration poll logic — the threaded loop is a thin wrapper."""

    @staticmethod
    def _completed_payload(conclusion: str = "SUCCESS") -> dict:
        return {
            "statusCheckRollup": [
                {"status": "COMPLETED", "conclusion": conclusion},
            ]
        }

    @staticmethod
    def _pending_payload() -> dict:
        return {
            "statusCheckRollup": [
                {"status": "COMPLETED", "conclusion": "SUCCESS"},
                {"status": "IN_PROGRESS", "conclusion": ""},
            ]
        }

    def test_poll_once_sigconts_when_all_checks_completed_success(
        self, tmp_project: Path
    ):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(returncode=0, stdout=json.dumps(self._completed_payload()))
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is True
        assert resume_event.is_set()
        mock_cont.assert_called_once_with(4242)

    def test_poll_once_sigconts_when_all_checks_completed_failure(
        self, tmp_project: Path
    ):
        """A failed CI is also a wake-up signal — agent needs to fix it."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(
            returncode=0, stdout=json.dumps(self._completed_payload("FAILURE"))
        )
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is True
        mock_cont.assert_called_once_with(4242)

    def test_poll_once_no_sigcont_when_any_check_pending(self, tmp_project: Path):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(returncode=0, stdout=json.dumps(self._pending_payload()))
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is False
        assert not resume_event.is_set()
        mock_cont.assert_not_called()

    def test_poll_once_no_double_sigcont_when_event_already_set(
        self, tmp_project: Path
    ):
        """Race-with-defensive-timer: if the timer SIGCONT'd first and
        set the event, the poller must NOT re-fire SIGCONT. The agent
        could already be processing post-resume work and a stray
        SIGCONT against an already-running pid is harmless but the
        log line would be misleading."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        resume_event.set()  # defensive timer already won the race
        proc = MagicMock(returncode=0, stdout=json.dumps(self._completed_payload()))
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is False
        mock_cont.assert_not_called()

    def test_poll_once_swallows_subprocess_timeout(self, tmp_project: Path):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="gh", timeout=30),
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is False
        assert not resume_event.is_set()
        mock_cont.assert_not_called()

    def test_poll_once_swallows_bad_json(self, tmp_project: Path):
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(returncode=0, stdout="not json")
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is False
        mock_cont.assert_not_called()

    def test_poll_once_swallows_nonzero_returncode(self, tmp_project: Path):
        """gh might exit non-zero on auth issues or rate limits — sleep+retry."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(returncode=1, stdout="", stderr="rate limit")
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ),
            patch("tripwire.runtimes.monitor_actions.send_sigcont") as mock_cont,
        ):
            fired = executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert fired is False
        mock_cont.assert_not_called()

    def test_poll_once_runs_gh_from_code_worktree(self, tmp_project: Path):
        """The `gh` invocation must use cwd=code_worktree so it inherits
        the agent's git remote. Without this, the poll would miss the
        PR or hit the wrong repo."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        proc = MagicMock(returncode=0, stdout=json.dumps(self._completed_payload()))
        with (
            patch(
                "tripwire.runtimes.monitor_actions.subprocess.run", return_value=proc
            ) as mock_run,
            patch("tripwire.runtimes.monitor_actions.send_sigcont"),
        ):
            executor._gh_poll_once(
                pid=4242,
                pr_number=42,
                code_worktree=Path("/tmp/agent-wt"),
                resume_event=resume_event,
                source_tripwire_id="monitor/ci_wait_suspend",
            )
        assert mock_run.called
        kwargs = mock_run.call_args.kwargs
        assert kwargs.get("cwd") == "/tmp/agent-wt"
        argv = mock_run.call_args.args[0]
        assert argv[0] == "gh"
        assert "pr" in argv and "view" in argv
        assert "42" in argv
        assert "statusCheckRollup" in argv

    def test_defensive_timer_sets_resume_event(self, tmp_project: Path):
        """When the defensive timer fires, it must set the per-pid
        event so any still-running poll thread exits without
        re-SIGCONT'ing."""
        executor = ActionExecutor(project_dir=tmp_project, session_id="s1")
        resume_event = threading.Event()
        executor._resume_events[4242] = resume_event
        with patch("tripwire.runtimes.monitor_actions.send_sigcont"):
            executor._defensive_resume(4242, "monitor/ci_wait_suspend")
        assert resume_event.is_set()
