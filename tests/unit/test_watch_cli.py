"""Tests for ``tripwire watch`` CLI commands."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from tripwire.cli.watch import watch_cmd


@pytest.fixture
def project(tmp_path: Path, save_test_session) -> Path:
    (tmp_path / "project.yaml").write_text(
        "name: tmp\nkey_prefix: TMP\nnext_issue_number: 1\n"
        "next_session_number: 1\nrepos:\n  SeidoAI/code:\n"
        "    local: /tmp/code\n"
    )
    for sub in ("issues", "nodes", "sessions", "docs", "plans"):
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    save_test_session(tmp_path, "s1", plan=True, status="executing")
    return tmp_path


def test_watch_status_reports_not_running(project: Path):
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["status", "--project-dir", str(project)])
    assert result.exit_code == 0
    assert "not running" in result.output.lower()


def test_watch_status_reports_running_with_pid(project: Path):
    """When the pidfile exists and the pid is alive, status reports it."""
    from tripwire.core.pr_watcher_daemon import write_pidfile

    write_pidfile(project, os.getpid())
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["status", "--project-dir", str(project)])
    assert result.exit_code == 0
    assert "running" in result.output.lower()
    assert str(os.getpid()) in result.output


def test_watch_start_foreground_invokes_run_forever(project: Path):
    """Foreground mode: blocks on WatchDaemon.run_forever()."""
    fake_daemon = MagicMock()
    runner = CliRunner()
    with patch("tripwire.cli.watch.WatchDaemon", return_value=fake_daemon) as mock_cls:
        result = runner.invoke(
            watch_cmd,
            ["start", "--project-dir", str(project), "--poll-interval", "0.05"],
        )
    assert result.exit_code == 0
    fake_daemon.run_forever.assert_called_once()
    cfg = mock_cls.call_args[0][0]
    assert cfg.poll_interval == 0.05


def test_watch_start_background_spawns_detached_subprocess(project: Path):
    """--background spawns a detached subprocess and returns immediately."""
    fake_proc = MagicMock()
    fake_proc.pid = 4242
    runner = CliRunner()
    with patch(
        "tripwire.cli.watch.subprocess.Popen", return_value=fake_proc
    ) as mock_popen:
        result = runner.invoke(
            watch_cmd, ["start", "--background", "--project-dir", str(project)]
        )
    assert result.exit_code == 0
    mock_popen.assert_called_once()
    # The detached process must opt into a new session so it survives
    # the parent shell.
    kwargs = mock_popen.call_args[1]
    assert kwargs.get("start_new_session") is True
    # PID is reported back to the operator.
    assert "4242" in result.output


def test_watch_start_refuses_when_already_running(project: Path):
    from tripwire.core.pr_watcher_daemon import write_pidfile

    write_pidfile(project, os.getpid())
    runner = CliRunner()
    result = runner.invoke(
        watch_cmd, ["start", "--background", "--project-dir", str(project)]
    )
    assert result.exit_code != 0
    assert "already running" in result.output.lower()


def test_watch_stop_sends_sigterm_to_pid(project: Path):
    from tripwire.core.pr_watcher_daemon import write_pidfile

    write_pidfile(project, 9999)
    runner = CliRunner()
    with patch("tripwire.cli.watch.send_sigterm", return_value=True) as mock_term:
        result = runner.invoke(watch_cmd, ["stop", "--project-dir", str(project)])
    assert result.exit_code == 0
    mock_term.assert_called_once_with(9999)


def test_watch_stop_no_op_when_not_running(project: Path):
    runner = CliRunner()
    result = runner.invoke(watch_cmd, ["stop", "--project-dir", str(project)])
    assert result.exit_code == 0
    assert "not running" in result.output.lower()


def test_watch_logs_tail_emits_log_contents(project: Path):
    from tripwire.core.pr_watcher_daemon import logfile_path

    log = logfile_path(project)
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("first line\nsecond line\n")
    runner = CliRunner()
    result = runner.invoke(
        watch_cmd, ["logs", "--project-dir", str(project), "--no-follow"]
    )
    assert result.exit_code == 0
    assert "first line" in result.output
    assert "second line" in result.output


def test_watch_logs_handles_missing_logfile(project: Path):
    runner = CliRunner()
    result = runner.invoke(
        watch_cmd, ["logs", "--project-dir", str(project), "--no-follow"]
    )
    # Exits cleanly with an informative message when log doesn't exist.
    assert result.exit_code == 0
    assert "no log" in result.output.lower() or "not yet" in result.output.lower()
