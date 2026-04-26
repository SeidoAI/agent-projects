"""``tripwire session cost <sid>`` CLI (KUI-96 §E2)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd


def _write_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def _assistant_event(model: str, usage: dict) -> dict:
    return {"type": "assistant", "message": {"model": model, "usage": usage}}


def test_session_cost_table_output(save_test_session, tmp_path_project: Path) -> None:
    """``session cost <sid>`` prints a per-category breakdown by default."""
    log = tmp_path_project / "sessions" / "demo" / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 500}
            )
        ],
    )
    save_test_session(
        tmp_path_project,
        session_id="demo",
        runtime_state={"log_path": str(log)},
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["cost", "demo", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code == 0, result.output
    assert "demo" in result.output
    # Total is $0.0525 — accept any sane formatting that contains the digits.
    assert "0.0525" in result.output or "0.05" in result.output
    assert "input" in result.output.lower()
    assert "output" in result.output.lower()


def test_session_cost_json_output(save_test_session, tmp_path_project: Path) -> None:
    """``--format json`` returns the breakdown as a parseable object."""
    log = tmp_path_project / "sessions" / "demo" / "session.log"
    _write_log(
        log,
        [
            _assistant_event(
                "claude-opus-4-7", {"input_tokens": 1000, "output_tokens": 500}
            )
        ],
    )
    save_test_session(
        tmp_path_project,
        session_id="demo",
        runtime_state={"log_path": str(log)},
    )
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["cost", "demo", "--project-dir", str(tmp_path_project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["session_id"] == "demo"
    assert abs(payload["total_usd"] - 0.0525) < 1e-9
    assert payload["input_usd"] > 0
    assert payload["output_usd"] > 0
    assert payload["cache_read_usd"] == 0
    assert payload["cache_write_usd"] == 0
    assert payload["input_tokens"] == 1000
    assert payload["output_tokens"] == 500


def test_session_cost_no_log_returns_zero(
    save_test_session, tmp_path_project: Path
) -> None:
    """A session that has never spawned (no ``log_path``) returns total_usd 0."""
    save_test_session(tmp_path_project, session_id="demo")
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["cost", "demo", "--project-dir", str(tmp_path_project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["total_usd"] == 0.0


def test_session_cost_unknown_session_errors(tmp_path_project: Path) -> None:
    """Asking for cost on a non-existent session is a click error."""
    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["cost", "nope", "--project-dir", str(tmp_path_project)],
    )
    assert result.exit_code != 0
    assert "nope" in result.output.lower() or "not found" in result.output.lower()
