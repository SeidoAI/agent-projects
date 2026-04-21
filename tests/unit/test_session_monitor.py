"""session_monitor.take_snapshot + detect_stuck."""

import os
import time
from pathlib import Path

import pytest

from tripwire.core.session_monitor import detect_stuck, take_snapshot


def test_snapshot_from_log(tmp_path: Path, tmp_path_project: Path, save_test_session):
    log = tmp_path / "session.log"
    log.write_text(
        '{"type":"assistant","message":"I will start","turn":1}\n'
        '{"type":"tool_use","tool":"Edit","input":{"file_path":"x.py"},"turn":2}\n'
        '{"type":"usage","total_tokens":5000,"cost_usd":0.20,"turn":2}\n',
        encoding="utf-8",
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={
            "pid": None,  # is_alive treats None gracefully
            "log_path": str(log),
            "claude_session_id": "sid",
        },
    )

    snap = take_snapshot(tmp_path_project, "s1")
    assert snap.source == "stream-json"
    assert snap.latest_tool == "Edit"
    assert snap.total_cost_usd == pytest.approx(0.20)
    assert snap.turn == 2
    assert snap.latest_tool_input == {"file_path": "x.py"}


def test_snapshot_ignores_errors_from_stream(
    tmp_path: Path, tmp_path_project: Path, save_test_session
):
    log = tmp_path / "session.log"
    log.write_text(
        '{"type":"error","message":"rate limit hit"}\n'
        '{"type":"tool_use","tool":"Edit","turn":1}\n',
        encoding="utf-8",
    )
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={"log_path": str(log), "claude_session_id": "sid"},
    )

    snap = take_snapshot(tmp_path_project, "s1")
    assert "rate limit hit" in snap.errors[0]


def test_snapshot_falls_back_to_polling_when_log_missing(
    tmp_path_project: Path, save_test_session
):
    save_test_session(
        tmp_path_project,
        "s1",
        status="executing",
        runtime_state={
            "log_path": "/nope/missing.log",
            "claude_session_id": "sid",
        },
    )
    snap = take_snapshot(tmp_path_project, "s1")
    # Source is "no-data" if polling finds nothing; "polling" if it finds branch/pr.
    assert snap.source in {"polling", "no-data"}


def test_detect_stuck_true_when_log_old(tmp_path: Path):
    log = tmp_path / "session.log"
    log.write_text("", encoding="utf-8")
    past = time.time() - 30 * 60  # 30 min ago
    os.utime(log, (past, past))
    assert detect_stuck(log, threshold_minutes=10) is True


def test_detect_stuck_false_when_log_recent(tmp_path: Path):
    log = tmp_path / "session.log"
    log.write_text("", encoding="utf-8")
    assert detect_stuck(log, threshold_minutes=10) is False


def test_detect_stuck_false_when_log_missing(tmp_path: Path):
    log = tmp_path / "never-existed.log"
    assert detect_stuck(log, threshold_minutes=10) is False
