"""Parse stream-json output from `claude -p --output-format stream-json`.

Each line is a JSON object with a `type` discriminator. This module maps
known event types to `StreamEvent.kind` and preserves unknown types as
`kind="info"` with the raw dict attached — forward-compat for new event
shapes without client updates.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_KNOWN_KINDS = {"tool_use", "tool_result", "assistant", "error", "usage"}


@dataclass
class StreamEvent:
    kind: str  # tool_use | tool_result | assistant | error | usage | info
    turn: int | None = None
    tool: str | None = None
    content: Any | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    raw: dict | None = None


def parse_event(line: str) -> StreamEvent | None:
    """Parse one JSONL line into a StreamEvent. None on malformed input."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    event_type = data.get("type", "info")
    kind = event_type if event_type in _KNOWN_KINDS else "info"

    return StreamEvent(
        kind=kind,
        turn=data.get("turn"),
        tool=data.get("tool"),
        content=(data.get("content") or data.get("message") or data.get("output")),
        total_tokens=data.get("total_tokens"),
        cost_usd=data.get("cost_usd"),
        raw=data,
    )
