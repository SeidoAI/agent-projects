"""Tests for tripwire.core.codex_stream — codex exec --json parser.

Fixture lines below are taken from a real `codex exec --json` invocation
(codex-cli v0.125.0). The parser maps codex's event vocabulary onto the
same :class:`StreamEvent` shape the claude stream uses, so downstream
consumers (the runtime monitor, log views) don't need to know which
provider produced the line.
"""

from __future__ import annotations

import json

from tripwire.core.codex_stream import parse_event


def test_parse_thread_started_returns_info_event():
    line = '{"type":"thread.started","thread_id":"abc-123"}'
    ev = parse_event(line)
    assert ev is not None
    assert ev.kind == "info"
    assert ev.raw["thread_id"] == "abc-123"


def test_parse_turn_started_returns_info_event():
    ev = parse_event('{"type":"turn.started"}')
    assert ev is not None
    assert ev.kind == "info"


def test_parse_command_execution_in_progress_yields_tool_use():
    line = (
        '{"type":"item.started","item":{"id":"item_0",'
        '"type":"command_execution","command":"/bin/zsh -lc \'echo hi\'",'
        '"aggregated_output":"","exit_code":null,"status":"in_progress"}}'
    )
    ev = parse_event(line)
    assert ev is not None
    assert ev.kind == "tool_use"
    assert ev.tool == "command_execution"
    # The command itself surfaces as content so the log tailer can show
    # what's being run.
    assert ev.content == "/bin/zsh -lc 'echo hi'"


def test_parse_command_execution_completed_yields_tool_result():
    line = (
        '{"type":"item.completed","item":{"id":"item_0",'
        '"type":"command_execution","command":"echo hi",'
        '"aggregated_output":"hi\\n","exit_code":0,"status":"completed"}}'
    )
    ev = parse_event(line)
    assert ev is not None
    assert ev.kind == "tool_result"
    assert ev.tool == "command_execution"
    assert ev.content == "hi\n"


def test_parse_agent_message_yields_assistant_event():
    line = (
        '{"type":"item.completed","item":{"id":"item_1",'
        '"type":"agent_message","text":"all done"}}'
    )
    ev = parse_event(line)
    assert ev is not None
    assert ev.kind == "assistant"
    assert ev.content == "all done"


def test_parse_turn_completed_yields_usage_event_with_total_tokens():
    """Codex's `turn.completed` carries the token accounting; sum
    input + output + reasoning into total_tokens so the monitor can
    enforce max-budget-usd from a usage stream."""
    payload = {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 1000,
            "cached_input_tokens": 200,
            "output_tokens": 50,
            "reasoning_output_tokens": 25,
        },
    }
    ev = parse_event(json.dumps(payload))
    assert ev is not None
    assert ev.kind == "usage"
    # 1000 + 50 + 25 = 1075. cached_input_tokens is informational only
    # and is NOT double-counted.
    assert ev.total_tokens == 1075
    # codex doesn't expose USD inline; cost_usd is computed downstream
    # from a price table. Leave it None.
    assert ev.cost_usd is None


def test_parse_unknown_type_falls_back_to_info_with_raw():
    payload = {"type": "some.future.event", "weird": True}
    ev = parse_event(json.dumps(payload))
    assert ev is not None
    assert ev.kind == "info"
    assert ev.raw == payload


def test_parse_blank_or_invalid_returns_none():
    assert parse_event("") is None
    assert parse_event("   ") is None
    assert parse_event("not-json") is None
    # JSON list, not object — codex always emits objects, so reject.
    assert parse_event('["not", "an", "object"]') is None


def test_parse_handles_partial_usage_block():
    """Some `turn.completed` events may omit reasoning_output_tokens;
    the parser must not raise."""
    payload = {
        "type": "turn.completed",
        "usage": {"input_tokens": 100, "output_tokens": 5},
    }
    ev = parse_event(json.dumps(payload))
    assert ev is not None
    assert ev.kind == "usage"
    assert ev.total_tokens == 105
