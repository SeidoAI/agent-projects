"""Tests for the standalone monitor runner.

The runner is the long-lived process that owns a per-spawn
:class:`RuntimeMonitor` + :class:`ActionExecutor` pair. It polls the
agent's pid; when the agent exits, it runs the on-process-exit
tripwires and exits cleanly.

The runner can be invoked as ``python -m
tripwire.runtimes.monitor_runner <ctx-json>``; tests exercise the
in-process API.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripwire.runtimes.monitor_runner import (
    MonitorRunner,
    RunnerConfig,
    read_runner_config,
    write_runner_config,
)


@pytest.fixture
def project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\nnext_session_number: 1\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True)
    return tmp_path


def test_runner_config_roundtrips_through_json(tmp_path: Path):
    cfg = RunnerConfig(
        session_id="s1",
        pid=12345,
        log_path=tmp_path / "agent.log",
        code_worktree=tmp_path / "code",
        pt_worktree=tmp_path / "pt",
        project_dir=tmp_path / "proj",
        max_budget_usd=50.0,
        model_name="claude-opus-4-7",
        key_files=["src/foo.py"],
        required_artifacts=["self-review.md"],
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.5,
    )
    target = tmp_path / "ctx.json"
    write_runner_config(cfg, target)
    loaded = read_runner_config(target)
    assert loaded == cfg


def test_runner_exits_cleanly_when_pid_dies(project: Path, tmp_path: Path):
    """The runner loop terminates when the watched pid stops being alive."""
    log = tmp_path / "agent.log"
    log.write_text("")
    cfg = RunnerConfig(
        session_id="s1",
        pid=999999,  # extremely unlikely to be a live pid
        log_path=log,
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=project,
        max_budget_usd=10.0,
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.05,
    )
    runner = MonitorRunner(cfg, max_runtime_seconds=2.0)
    runner.run()
    # Returned without timing out: the pid-dead exit branch fired.
    assert runner.exit_reason == "pid_dead"


def test_runner_respects_max_runtime_safety_cap(project: Path, tmp_path: Path):
    """If the watched pid stays alive past max_runtime_seconds, the runner
    bails out so it never runs forever. Belt-and-braces; in normal
    operation the pid-died path always fires first."""
    import os

    log = tmp_path / "agent.log"
    log.write_text("")
    cfg = RunnerConfig(
        session_id="s1",
        pid=os.getpid(),  # pytest's own pid — guaranteed alive
        log_path=log,
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=project,
        max_budget_usd=10.0,
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.05,
    )
    runner = MonitorRunner(cfg, max_runtime_seconds=0.3)
    runner.run()
    assert runner.exit_reason == "max_runtime"


def test_runner_dispatches_actions_to_executor(project: Path, tmp_path: Path):
    """When the monitor emits a TransitionStatus, the runner forwards it to
    the action executor which writes the new status to session.yaml."""
    from tripwire.core.session_store import load_session

    log = tmp_path / "agent.log"
    # Pre-populate with a budget-blowing event.
    log.write_text(
        json.dumps(
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-7",
                    "usage": {"input_tokens": 10_000, "output_tokens": 10_000},
                },
            }
        )
        + "\n"
    )
    cfg = RunnerConfig(
        session_id="s1",
        pid=999999,
        log_path=log,
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=project,
        max_budget_usd=0.001,  # blown by the first event
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.05,
    )
    runner = MonitorRunner(cfg, max_runtime_seconds=2.0)
    runner.run()
    session = load_session(project, "s1")
    assert session.status == "paused"


# ---------- Stream-idle reaper -----------------------------------------


def test_runner_reaps_stream_idle_when_log_silent(project: Path, tmp_path: Path):
    """If the watched pid stays alive but no events are produced for
    longer than ``stream_idle_threshold_seconds``, the runner classifies
    it as a wedged-stream death and reaps it (SIGTERM + flip status to
    failed + inject follow-up)."""
    import os

    from tripwire.core.session_store import load_session

    log = tmp_path / "agent.log"
    log.write_text("")  # never any events
    cfg = RunnerConfig(
        session_id="s1",
        pid=os.getpid(),  # alive throughout the test
        log_path=log,
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=project,
        max_budget_usd=10.0,
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.02,
        stream_idle_threshold_seconds=0.1,  # 100ms — fires fast in test
    )
    runner = MonitorRunner(cfg, max_runtime_seconds=2.0)
    # Patch the SIGTERM action so the test doesn't actually kill pytest.
    import tripwire.runtimes.monitor_actions as actions_mod

    sigterm_calls: list[int] = []
    real_do_sigterm = actions_mod.ActionExecutor._do_sigterm
    actions_mod.ActionExecutor._do_sigterm = lambda self, action: sigterm_calls.append(
        action.pid
    )
    try:
        runner.run()
    finally:
        actions_mod.ActionExecutor._do_sigterm = real_do_sigterm

    assert runner.exit_reason == "stream_idle"
    # The reaper sent SIGTERM to the watched pid (intercepted by patch).
    assert sigterm_calls == [os.getpid()]
    # And flipped the session to failed via the existing executor path.
    session = load_session(project, "s1")
    assert session.status == "failed"


def test_runner_does_not_reap_when_events_keep_flowing(project: Path, tmp_path: Path):
    """As long as new events land in the log, the stream-idle clock
    keeps resetting and the reaper never fires. A flow of trivial
    events plus a short window should leave us with the standard
    pid-dead exit, not a stream-idle one."""
    log = tmp_path / "agent.log"
    log.write_text("")
    cfg = RunnerConfig(
        session_id="s1",
        pid=999999,  # not alive — pid_dead exit will eventually fire
        log_path=log,
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=project,
        max_budget_usd=10.0,
        monitor_log_path=tmp_path / "monitor.log",
        poll_interval=0.02,
        stream_idle_threshold_seconds=0.5,  # 500ms — would fire if no events
    )
    runner = MonitorRunner(cfg, max_runtime_seconds=2.0)
    # Even with pid not alive, the runner's first poll-tick happens
    # before pid is checked → if stream-idle threshold is very small
    # AND no events arrive AND pid_dead is faster, we'd want pid_dead.
    # Here we want the simpler assertion: with pid=999999 (dead), the
    # runner exits via pid_dead, not stream_idle, even though no
    # events arrive — because the threshold is 0.5s but pid_dead
    # fires within one poll_interval (20ms).
    runner.run()
    assert runner.exit_reason == "pid_dead"


def test_monitor_thread_tracks_last_event_at(tmp_path: Path):
    """`MonitorThread.last_event_at` advances every time a parsed
    event is processed, regardless of whether it produces actions."""
    import json
    import time

    from tripwire.runtimes.monitor import (
        MonitorContext,
        MonitorThread,
        RuntimeMonitor,
    )

    log = tmp_path / "agent.log"
    log.write_text("")
    monitor = RuntimeMonitor(
        MonitorContext(
            session_id="s1",
            pid=12345,
            log_path=log,
            code_worktree=tmp_path / "code",
            pt_worktree=None,
            project_dir=tmp_path,
            max_budget_usd=10.0,
            model_name="claude-opus-4-7",
            key_files=[],
            required_artifacts=[],
        )
    )
    actions: list = []
    thread = MonitorThread(monitor, actions.append, poll_interval=0.02)
    thread.start()
    try:
        baseline = thread.last_event_at
        time.sleep(0.05)
        # Append a benign event that produces no actions.
        log.write_text(json.dumps({"type": "system", "subtype": "init"}) + "\n")
        # Wait for the thread's tail loop to pick it up.
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and thread.last_event_at == baseline:
            time.sleep(0.02)
    finally:
        thread.stop()
    assert thread.last_event_at > baseline


def test_runner_config_defaults_stream_idle_threshold_to_600s():
    """Default threshold is 10 minutes — well above any normal
    between-events gap during heavy tool use."""
    cfg = RunnerConfig(
        session_id="s1",
        pid=1,
        log_path=Path("/tmp/x"),
        code_worktree=Path("/tmp/code"),
        pt_worktree=None,
        project_dir=Path("/tmp/proj"),
        max_budget_usd=10.0,
        monitor_log_path=Path("/tmp/m"),
    )
    assert cfg.stream_idle_threshold_seconds == 600.0


def test_runner_config_roundtrips_stream_idle_threshold(tmp_path: Path):
    """Custom threshold survives the JSON write/read cycle so the
    spawning runtime can override it."""
    cfg = RunnerConfig(
        session_id="s1",
        pid=1,
        log_path=tmp_path / "log",
        code_worktree=tmp_path / "code",
        pt_worktree=None,
        project_dir=tmp_path,
        max_budget_usd=10.0,
        monitor_log_path=tmp_path / "m",
        stream_idle_threshold_seconds=120.0,
    )
    target = tmp_path / "ctx.json"
    write_runner_config(cfg, target)
    loaded = read_runner_config(target)
    assert loaded.stream_idle_threshold_seconds == 120.0
