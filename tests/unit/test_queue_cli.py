"""``tripwire queue`` CLI (KUI-96 §E1)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.queue import queue_cmd
from tripwire.core.queue_runner import (
    pidfile_path,
    write_pidfile,
)


def test_queue_status_no_pidfile(tmp_path: Path) -> None:
    """Status reports `not running` when no pidfile exists."""
    runner = CliRunner()
    result = runner.invoke(queue_cmd, ["status", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "not running" in result.output.lower()


def test_queue_start_foreground_with_max_ticks(
    save_test_session, tmp_path_project: Path, monkeypatch
) -> None:
    """``start`` with ``--max-ticks 1`` runs once and exits, even if no
    queued sessions exist (idle tick)."""
    runner = CliRunner()
    result = runner.invoke(
        queue_cmd,
        [
            "start",
            "--project-dir",
            str(tmp_path_project),
            "--max-ticks",
            "1",
            "--tick-sleep",
            "0",
        ],
    )
    assert result.exit_code == 0, result.output
    # No pidfile remaining after run-forever returns.
    assert not pidfile_path(tmp_path_project).exists()


def test_queue_start_refuses_when_already_running(
    tmp_path_project: Path,
) -> None:
    """A pidfile pointing at our own (live) PID blocks a second start."""
    import os

    write_pidfile(tmp_path_project, os.getpid())
    runner = CliRunner()
    result = runner.invoke(
        queue_cmd,
        [
            "start",
            "--project-dir",
            str(tmp_path_project),
            "--max-ticks",
            "1",
            "--tick-sleep",
            "0",
        ],
    )
    # ClickException → exit 1.
    assert result.exit_code != 0
    assert "already running" in result.output.lower()


def test_queue_stop_no_pidfile(tmp_path: Path) -> None:
    """Stop is a no-op when no pidfile exists."""
    runner = CliRunner()
    result = runner.invoke(queue_cmd, ["stop", "--project-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "not running" in result.output.lower()
