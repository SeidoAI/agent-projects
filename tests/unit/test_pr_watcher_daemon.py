"""Tests for the watch daemon harness (the looped runner)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tripwire.core.pr_watcher_daemon import (
    DaemonConfig,
    WatchDaemon,
    build_watched_sessions,
    is_daemon_running,
    pidfile_path,
    write_pidfile,
)


@pytest.fixture
def project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\n"
        "next_session_number: 1\nrepos:\n  SeidoAI/code:\n"
        "    local: /tmp/code\nartifact_manifest:\n"
        "  session_required: [self-review.md, insights.yaml]\n"
        "  issue_required: [developer.md]\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True, status="executing")
    return tmp_path


def test_build_watched_sessions_filters_inactive(project: Path, save_test_session):
    save_test_session(project, "s_done", plan=False, status="done")
    save_test_session(
        project,
        "s_active",
        plan=True,
        status="executing",
        repos=[
            {
                "repo": "SeidoAI/code",
                "base_branch": "main",
                "branch": "feat/s_active",
                "pr_number": 42,
            }
        ],
    )
    with patch(
        "tripwire.core.pr_watcher_daemon._project_repo_slug",
        return_value="ExampleOrg/example-project",
    ):
        sessions = build_watched_sessions(project)
    ids = {ws.session_id for ws in sessions}
    assert "s_active" in ids
    assert "s_done" not in ids
    s = next(ws for ws in sessions if ws.session_id == "s_active")
    assert s.code_repo == "SeidoAI/code"
    assert s.code_pr_number == 42
    assert s.code_branch == "feat/s_active"
    assert s.pt_repo == "ExampleOrg/example-project"
    assert s.pt_branch == "proj/s_active"
    # required_artifacts populated from project.yaml manifest, prefixed
    # with the session-specific path so file-list comparisons work.
    assert "sessions/s_active/self-review.md" in s.required_artifacts
    assert "sessions/s_active/insights.yaml" in s.required_artifacts


def test_pidfile_lifecycle(tmp_path: Path):
    pid_path = pidfile_path(tmp_path)
    assert not pid_path.exists()
    write_pidfile(tmp_path, 12345)
    assert pid_path.exists()
    assert pid_path.read_text().strip() == "12345"


def test_is_daemon_running_returns_false_for_dead_pid(tmp_path: Path):
    write_pidfile(tmp_path, 999999)  # extremely unlikely to be alive
    assert is_daemon_running(tmp_path) is False


def test_is_daemon_running_returns_false_when_no_pidfile(tmp_path: Path):
    assert is_daemon_running(tmp_path) is False


def test_is_daemon_running_returns_true_for_live_pid(tmp_path: Path):
    import os

    write_pidfile(tmp_path, os.getpid())
    assert is_daemon_running(tmp_path) is True


def test_daemon_one_tick_invokes_watcher_and_executor(project: Path, save_test_session):
    """One tick: build sessions, run watcher.tick, dispatch actions."""
    save_test_session(
        project,
        "s_active",
        plan=True,
        status="executing",
        repos=[
            {
                "repo": "SeidoAI/code",
                "base_branch": "main",
                "branch": "feat/s_active",
                "pr_number": 42,
            }
        ],
    )

    fake_watcher = MagicMock()
    fake_executor = MagicMock()
    fake_watcher.tick.return_value = ["action_a", "action_b"]
    cfg = DaemonConfig(project_dir=project, poll_interval=0.05)
    daemon = WatchDaemon(cfg, watcher=fake_watcher, executor=fake_executor)

    with patch(
        "tripwire.core.pr_watcher_daemon._project_repo_slug",
        return_value="ExampleOrg/example-project",
    ):
        daemon.tick(now=datetime.now(tz=timezone.utc))

    fake_watcher.tick.assert_called_once()
    fake_executor.execute.assert_any_call("action_a")
    fake_executor.execute.assert_any_call("action_b")


def test_daemon_run_forever_respects_stop_event(project: Path):
    fake_watcher = MagicMock()
    fake_watcher.tick.return_value = []
    cfg = DaemonConfig(project_dir=project, poll_interval=0.05)
    daemon = WatchDaemon(cfg, watcher=fake_watcher, executor=MagicMock())

    import threading

    stopper = threading.Timer(0.2, daemon.stop)
    stopper.start()
    with patch(
        "tripwire.core.pr_watcher_daemon._project_repo_slug",
        return_value="ExampleOrg/example-project",
    ):
        daemon.run_forever()
    stopper.cancel()
    assert fake_watcher.tick.call_count >= 1
