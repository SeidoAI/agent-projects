"""Session monitor snapshot — stream-json primary, git/gh fallback.

Produces a `MonitorSnapshot` summarising what an executing session is doing
right now: current turn, running cost, latest tool call, branch head, PR
status, stuck detection, process liveness.

Preference order for the data source:
  - `stream-json`: read from claude's JSONL log (richest, lowest latency)
  - `polling`: fall back to `git log` + `gh pr list` when no log exists yet
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from tripwire.core.session_store import load_session
from tripwire.core.stream_json import parse_event


@dataclass
class MonitorSnapshot:
    session_id: str
    status: str
    source: str  # "stream-json" | "polling" | "no-data"
    turn: int | None = None
    total_cost_usd: float | None = None
    latest_tool: str | None = None
    latest_tool_input: dict | None = None
    pr_number: int | None = None
    branch: str | None = None
    last_commit_sha: str | None = None
    process_alive: bool | None = None
    stuck: bool = False
    errors: list[str] = field(default_factory=list)


def take_snapshot(project_dir: Path, session_id: str) -> MonitorSnapshot:
    """Build a snapshot of one session's runtime state."""
    session = load_session(project_dir, session_id)
    snap = MonitorSnapshot(
        session_id=session_id,
        status=session.status,
        source="no-data",
    )

    log_path = session.runtime_state.log_path
    if log_path and Path(log_path).is_file():
        _populate_from_log(snap, Path(log_path))
        snap.source = "stream-json"
    else:
        _populate_from_polling(snap, project_dir, session)
        snap.source = "polling" if (snap.branch or snap.pr_number) else "no-data"

    pid = session.runtime_state.pid
    if pid:
        from tripwire.core.process_helpers import is_alive

        snap.process_alive = is_alive(pid)

    return snap


def _populate_from_log(snap: MonitorSnapshot, log: Path) -> None:
    latest_tool_event = None
    usage_event = None
    last_turn = None

    with log.open("r", encoding="utf-8") as f:
        for line in f:
            event = parse_event(line)
            if event is None:
                continue
            if event.kind == "tool_use":
                latest_tool_event = event
            elif event.kind == "usage":
                usage_event = event
            elif event.kind == "error":
                snap.errors.append(str(event.content))
            if event.turn is not None:
                last_turn = event.turn

    if latest_tool_event is not None:
        snap.latest_tool = latest_tool_event.tool
        if latest_tool_event.raw is not None:
            snap.latest_tool_input = latest_tool_event.raw.get("input")
    if usage_event is not None:
        snap.total_cost_usd = usage_event.cost_usd
    snap.turn = last_turn
    snap.stuck = detect_stuck(log, threshold_minutes=10)


def _populate_from_polling(snap: MonitorSnapshot, project_dir: Path, session) -> None:
    """Fall back to git/gh when no claude log is available."""
    wt = None
    for entry in session.runtime_state.worktrees:
        wt = Path(entry.worktree_path)
        snap.branch = entry.branch
        break
    if wt and wt.is_dir():
        try:
            result = subprocess.run(
                ["git", "-C", str(wt), "log", "-1", "--format=%h"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                snap.last_commit_sha = result.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            pass

    if snap.branch:
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--head",
                    snap.branch,
                    "--json",
                    "number",
                    "--limit",
                    "1",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                prs = json.loads(result.stdout)
                if prs:
                    snap.pr_number = prs[0].get("number")
        except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
            pass


def detect_stuck(log: Path, *, threshold_minutes: int = 10) -> bool:
    """True if the log's mtime is older than `threshold_minutes` ago."""
    if not log.is_file():
        return False
    age_seconds = time.time() - log.stat().st_mtime
    return age_seconds > threshold_minutes * 60
