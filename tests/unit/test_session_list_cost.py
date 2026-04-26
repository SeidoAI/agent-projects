"""``tripwire session list`` Cost column (KUI-96 §E2)."""

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


def test_session_list_json_includes_cost_usd(
    save_test_session, tmp_path_project: Path
) -> None:
    """``--format json`` exposes ``cost_usd`` per session."""
    log = tmp_path_project / "sessions" / "s1" / "session.log"
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
        session_id="s1",
        runtime_state={"log_path": str(log)},
    )
    save_test_session(tmp_path_project, session_id="s2")  # no log

    runner = CliRunner()
    result = runner.invoke(
        session_cmd,
        ["list", "--project-dir", str(tmp_path_project), "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    by_id = {s["id"]: s for s in payload}
    assert abs(by_id["s1"]["cost_usd"] - 0.0525) < 1e-9
    assert by_id["s2"]["cost_usd"] == 0.0


def test_session_list_table_renders_cost_column(
    save_test_session, tmp_path_project: Path
) -> None:
    """The default table view shows a Cost column for every row."""
    log = tmp_path_project / "sessions" / "s1" / "session.log"
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
        session_id="s1",
        runtime_state={"log_path": str(log)},
    )

    runner = CliRunner()
    result = runner.invoke(
        session_cmd, ["list", "--project-dir", str(tmp_path_project)]
    )
    assert result.exit_code == 0, result.output
    # Column header shows up in the table.
    assert "cost" in result.output.lower()
    # The non-zero amount renders with 4 decimals.
    assert "0.0525" in result.output or "$0.05" in result.output
