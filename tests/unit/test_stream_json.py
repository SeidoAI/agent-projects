"""stream-json parser tests."""

from tripwire.core.stream_json import parse_event


def test_parse_tool_use_event():
    line = '{"type":"tool_use","tool":"Edit","input":{"file_path":"x.py"},"turn":2}'
    event = parse_event(line)
    assert event is not None
    assert event.kind == "tool_use"
    assert event.tool == "Edit"
    assert event.turn == 2
    assert event.raw is not None
    assert event.raw["input"]["file_path"] == "x.py"


def test_parse_usage_event():
    line = '{"type":"usage","total_tokens":15234,"cost_usd":0.42,"turn":2}'
    event = parse_event(line)
    assert event is not None
    assert event.kind == "usage"
    assert event.cost_usd == 0.42
    assert event.total_tokens == 15234


def test_parse_assistant_event_with_message():
    line = '{"type":"assistant","message":"doing stuff","turn":1}'
    event = parse_event(line)
    assert event is not None
    assert event.kind == "assistant"
    assert event.content == "doing stuff"


def test_parse_error_event():
    line = '{"type":"error","message":"rate limit"}'
    event = parse_event(line)
    assert event is not None
    assert event.kind == "error"


def test_parse_unknown_event_preserved_as_info():
    line = '{"type":"completely_new_event_type","data":"something"}'
    event = parse_event(line)
    assert event is not None
    assert event.kind == "info"
    assert event.raw is not None
    assert event.raw["data"] == "something"


def test_parse_malformed_line_returns_none():
    assert parse_event("not json") is None
    assert parse_event("") is None
    assert parse_event("   ") is None


def test_parse_non_dict_json_returns_none():
    assert parse_event("[1,2,3]") is None
    assert parse_event('"string"') is None
