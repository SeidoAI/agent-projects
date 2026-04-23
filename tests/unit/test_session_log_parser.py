"""Tests for session_log_parser — H6."""

from __future__ import annotations

from pathlib import Path

import pytest

from tripwire.core.session_log_parser import SessionLogSummary, format_text, parse

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "stream-json"


class TestParseHappyPath:
    def test_full_summary_shape(self):
        summary = parse(_FIXTURES / "happy_path.log")
        assert isinstance(summary, SessionLogSummary)
        assert summary.claude_session_id == "uuid-happy"
        assert summary.started_at == "2026-04-23T12:00:00Z"
        assert summary.ended_at == "2026-04-23T12:05:30Z"
        assert summary.exit_subtype == "success"
        assert summary.tool_call_count == 2
        assert summary.tool_names == ["Read", "Bash"]
        assert summary.input_tokens == 12500
        assert summary.output_tokens == 800
        assert summary.duration_ms == 330000
        assert summary.cost_usd == pytest.approx(0.1234)
        assert "PR opened" in summary.final_text
        # No question mark → not flagged as stopped-to-ask.
        assert summary.stopped_to_ask is False


class TestParseErrorMaxTurns:
    def test_exit_subtype_and_no_question(self):
        summary = parse(_FIXTURES / "error_max_turns.log")
        assert summary.exit_subtype == "error_max_turns"
        assert summary.tool_call_count == 2
        # Max-turns is a failure, not a stop-and-ask.
        assert summary.stopped_to_ask is False
        assert summary.duration_ms == 900000


class TestParseStopAndAsk:
    def test_flagged_as_stopped_to_ask(self):
        summary = parse(_FIXTURES / "stop_and_ask.log")
        assert summary.exit_subtype == "success"
        assert "?" in summary.final_text
        assert summary.stopped_to_ask is True
        assert "retry count" in summary.final_text


class TestParseEdgeCases:
    def test_empty_log_yields_default_summary(self, tmp_path):
        log = tmp_path / "empty.log"
        log.write_text("", encoding="utf-8")
        summary = parse(log)
        assert summary.exit_subtype is None
        assert summary.tool_call_count == 0
        assert summary.final_text == ""
        assert summary.stopped_to_ask is False

    def test_malformed_lines_are_skipped(self, tmp_path):
        """Bad JSON lines don't abort the parse — the rest of the file
        still produces a valid summary."""
        log = tmp_path / "mixed.log"
        log.write_text(
            "\n".join(
                [
                    "not json at all",
                    '{"type":"system","subtype":"init","session_id":"u1","timestamp":"2026-04-23T12:00:00Z"}',
                    "{malformed",
                    '{"type":"result","subtype":"success","result":"done"}',
                ]
            ),
            encoding="utf-8",
        )
        summary = parse(log)
        assert summary.claude_session_id == "u1"
        assert summary.exit_subtype == "success"
        assert summary.final_text == "done"


class TestFormatText:
    def test_text_contains_key_sections(self):
        summary = parse(_FIXTURES / "happy_path.log")
        rendered = format_text(summary)
        assert "uuid-happy" in rendered
        assert "success" in rendered
        assert "Tool calls:   2" in rendered
        assert "PR opened" in rendered
        assert "STOPPED TO ASK" not in rendered

    def test_stopped_to_ask_banner_appears(self):
        summary = parse(_FIXTURES / "stop_and_ask.log")
        rendered = format_text(summary)
        assert "STOPPED TO ASK" in rendered
