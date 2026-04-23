"""Parse a claude stream-json log into a human-readable summary.

The subprocess runtime writes every claude event as one JSON object
per line (via ``--output-format stream-json``). This module walks
that file and extracts the signal a PM actually needs: did it
succeed, did it stop to ask, what did it say last, how much did it
cost. Pure function — no filesystem mutation, no side effects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SessionLogSummary:
    """Everything a PM typically wants to know after a spawn attempt."""

    log_path: Path
    claude_session_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    final_text: str = ""
    exit_subtype: str | None = None
    tool_call_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None
    cost_usd: float | None = None
    stopped_to_ask: bool = False


def _extract_last_text(content: list[dict[str, Any]] | None) -> str | None:
    if not content:
        return None
    for block in reversed(content):
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                return text
    return None


def _count_tools(content: list[dict[str, Any]] | None) -> list[str]:
    if not content:
        return []
    return [
        block.get("name", "<unnamed>")
        for block in content
        if block.get("type") == "tool_use"
    ]


def parse(log_path: Path) -> SessionLogSummary:
    """Walk the stream-json at ``log_path`` and return a summary.

    Unknown / malformed lines are skipped. A log that never produced
    a terminal ``result`` event yields a summary with
    ``exit_subtype=None`` — callers should treat that as "still
    running or crashed before claude could emit the result event."
    """
    summary = SessionLogSummary(log_path=log_path)

    for raw in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue

        event_type = event.get("type")
        if event_type == "system" and event.get("subtype") == "init":
            sid = event.get("session_id")
            if isinstance(sid, str):
                summary.claude_session_id = sid
            ts = event.get("timestamp")
            if isinstance(ts, str):
                summary.started_at = ts
        elif event_type == "assistant":
            msg = event.get("message") or {}
            content = msg.get("content")
            text = _extract_last_text(content)
            if text is not None:
                summary.final_text = text
            tool_names = _count_tools(content)
            if tool_names:
                summary.tool_call_count += len(tool_names)
                summary.tool_names.extend(tool_names)
        elif event_type == "result":
            subtype = event.get("subtype")
            if isinstance(subtype, str):
                summary.exit_subtype = subtype
            ended = event.get("timestamp")
            if isinstance(ended, str):
                summary.ended_at = ended
            dur = event.get("duration_ms")
            if isinstance(dur, int):
                summary.duration_ms = dur
            cost = event.get("total_cost_usd")
            if isinstance(cost, (int, float)):
                summary.cost_usd = float(cost)
            usage = event.get("usage") or {}
            in_tok = usage.get("input_tokens")
            out_tok = usage.get("output_tokens")
            if isinstance(in_tok, int):
                summary.input_tokens = in_tok
            if isinstance(out_tok, int):
                summary.output_tokens = out_tok
            # Some result events carry the final string in .result.
            result_text = event.get("result")
            if isinstance(result_text, str) and result_text.strip():
                summary.final_text = result_text

    # Stop-and-ask heuristic: the agent exited cleanly AND its final
    # text contains a question mark. Matches the empirically-observed
    # shape (probe #2 from the pivot notes: "natural ambiguity, no
    # explicit tool request → writes textual reasoning, exits success").
    if summary.exit_subtype == "success" and "?" in summary.final_text:
        summary.stopped_to_ask = True

    return summary


def format_text(summary: SessionLogSummary) -> str:
    """Render a summary as human-readable text for `session summary`."""
    lines: list[str] = []
    lines.append(f"Log:          {summary.log_path}")
    if summary.claude_session_id:
        lines.append(f"Claude UUID:  {summary.claude_session_id}")
    if summary.started_at:
        lines.append(f"Started:      {summary.started_at}")
    if summary.ended_at:
        lines.append(f"Ended:        {summary.ended_at}")
    if summary.duration_ms is not None:
        lines.append(f"Duration:     {summary.duration_ms / 1000:.1f}s")
    if summary.exit_subtype:
        lines.append(f"Exit:         {summary.exit_subtype}")
    else:
        lines.append("Exit:         (no terminal result event — still running?)")
    lines.append(f"Tool calls:   {summary.tool_call_count}")
    if summary.input_tokens is not None or summary.output_tokens is not None:
        lines.append(
            f"Tokens:       in={summary.input_tokens} out={summary.output_tokens}"
        )
    if summary.cost_usd is not None:
        lines.append(f"Cost:         ${summary.cost_usd:.4f}")
    if summary.stopped_to_ask:
        lines.append("")
        lines.append("STOPPED TO ASK — final text contains a question:")
    if summary.final_text:
        lines.append("")
        lines.append("Final assistant text:")
        for line in summary.final_text.splitlines() or [""]:
            lines.append(f"  {line}")
    return "\n".join(lines)
