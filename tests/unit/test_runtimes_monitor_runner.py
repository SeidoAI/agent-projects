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
    write_runner_config,
    read_runner_config,
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
