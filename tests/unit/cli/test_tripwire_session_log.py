"""Tests for `tripwire session log <sid>` — per-session tripwire log."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from tripwire.cli.main import cli


def _project(tmp_path: Path) -> None:
    (tmp_path / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "fixture",
                "key_prefix": "FIX",
                "base_branch": "main",
                "next_issue_number": 1,
                "next_session_number": 1,
                "phase": "scoping",
            }
        ),
        encoding="utf-8",
    )


def _write_event(tmp_path: Path, sid: str, n: int, payload: dict) -> None:
    fire_dir = tmp_path / ".tripwire" / "events" / "firings" / sid
    fire_dir.mkdir(parents=True, exist_ok=True)
    (fire_dir / f"{n:04d}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_session_log_no_events_says_so(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "log",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (
        "no tripwire fires" in result.output.lower()
        or "0 fires" in result.output.lower()
    )


def test_session_log_lists_fires_with_timestamps(tmp_path: Path) -> None:
    _project(tmp_path)
    _write_event(
        tmp_path,
        "fixture-1",
        1,
        {
            "kind": "tripwire_fire",
            "tripwire_id": "self-review",
            "session_id": "fixture-1",
            "fired_at": "2026-04-26T14:32:18+00:00",
            "event": "session.complete",
            "blocks": True,
            "ack": None,
            "ack_at": None,
            "fix_commits": [],
            "declared_no_findings": False,
            "escalated": False,
            "prompt_redacted": "<<self-review prompt — content withheld>>",
            "prompt_revealed": "the four-lens body",
        },
    )
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "log",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "self-review" in result.output
    assert "2026-04-26T14:32:18" in result.output
    # Without --reveal in non-PM mode, prompt body stays hidden.
    assert "the four-lens body" not in result.output


def test_session_log_ack_status_shown(tmp_path: Path) -> None:
    _project(tmp_path)
    _write_event(
        tmp_path,
        "fixture-1",
        1,
        {
            "kind": "tripwire_fire",
            "tripwire_id": "self-review",
            "session_id": "fixture-1",
            "fired_at": "2026-04-26T14:32:18+00:00",
            "event": "session.complete",
            "blocks": True,
            "ack": None,
        },
    )
    # Write the ack marker for fixture-1.
    marker = tmp_path / ".tripwire" / "acks" / "self-review-fixture-1.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"fix_commits": ["abc123"]}), encoding="utf-8")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "log",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "ack" in result.output.lower()
    assert "abc123" in result.output


def test_session_log_web_prints_deeplink(tmp_path: Path) -> None:
    _project(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "session",
            "log",
            "fixture-1",
            "--project-dir",
            str(tmp_path),
            "--web",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "tripwires" in result.output.lower()
    assert "fixture-1" in result.output
