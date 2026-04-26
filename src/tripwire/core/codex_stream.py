"""Parse JSONL output from `codex exec --json`.

Codex emits a different event vocabulary than claude does, but the
downstream consumers (the in-flight monitor, log views) work in terms
of the unified :class:`tripwire.core.stream_json.StreamEvent` shape.
This parser maps codex's events onto that shape so the monitor's cost
/ budget enforcement is provider-agnostic.

Event mapping (verified against codex-cli v0.125.0 output):

  - ``thread.started`` / ``turn.started`` → ``info``
  - ``item.started`` of subtype ``command_execution`` → ``tool_use``
  - ``item.completed`` of subtype ``command_execution`` → ``tool_result``
  - ``item.completed`` of subtype ``agent_message`` → ``assistant``
  - ``turn.completed`` (carries ``usage``) → ``usage``
  - anything else → ``info`` with raw kept for forward-compat

Notes:

  - Codex's usage block has ``input_tokens``, ``output_tokens``, and
    ``reasoning_output_tokens`` (sometimes absent). ``cached_input_tokens``
    is informational and NOT double-counted.
  - Codex does NOT emit ``cost_usd`` inline — the monitor computes USD
    from ``total_tokens`` x a model price table. ``cost_usd`` stays
    None on codex events.
"""

from __future__ import annotations

import json
from typing import Any

from tripwire.core.stream_json import StreamEvent


def _usage_to_total_tokens(usage: dict[str, Any]) -> int | None:
    if not isinstance(usage, dict):
        return None
    inp = usage.get("input_tokens") or 0
    out = usage.get("output_tokens") or 0
    reasoning = usage.get("reasoning_output_tokens") or 0
    total = int(inp) + int(out) + int(reasoning)
    return total or None


def parse_event(line: str) -> StreamEvent | None:
    """Parse one codex JSONL line into a :class:`StreamEvent`. None on
    blank/malformed input or non-object payloads."""
    line = line.strip()
    if not line:
        return None
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    event_type = data.get("type", "")

    if event_type == "turn.completed":
        usage = data.get("usage") or {}
        return StreamEvent(
            kind="usage",
            total_tokens=_usage_to_total_tokens(usage),
            cost_usd=None,
            raw=data,
        )

    if event_type in ("item.started", "item.completed"):
        item = data.get("item") or {}
        item_type = item.get("type")

        if item_type == "command_execution":
            kind = "tool_use" if event_type == "item.started" else "tool_result"
            content = (
                item.get("command")
                if event_type == "item.started"
                else item.get("aggregated_output")
            )
            return StreamEvent(
                kind=kind,
                tool="command_execution",
                content=content,
                raw=data,
            )

        if item_type == "agent_message" and event_type == "item.completed":
            return StreamEvent(
                kind="assistant",
                content=item.get("text"),
                raw=data,
            )

        # other item types (file_change, mcp_tool_call, …) — keep as info
        return StreamEvent(kind="info", raw=data)

    # thread.started, turn.started, errors emitted on stderr that landed
    # here, anything else: forward-compat as info.
    return StreamEvent(kind="info", raw=data)
