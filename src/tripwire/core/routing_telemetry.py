"""Routing telemetry log (KUI-96 §E4).

Every successful ``tripwire session complete`` appends one JSONL row
to ``<project>/sessions/.routing_telemetry.jsonl``. Each row records
the route the session ran on (provider/model/effort/task_kind), how
much it cost, how long it ran, how many re-engagements it took, and
whether the work merged. After 50+ sessions, the operator runs
``tripwire session analyze-routing`` to surface $/merged-PR per
route and flag tunings worth promoting to ``routing.yaml``.

The schema is append-only and column-stable: never rename or drop a
key — old rows must remain analysable. Add new keys at the end so
older readers can ignore them safely.

Why JSONL instead of YAML or sqlite: every row is independent and
self-describing; ``jq`` / ``pandas`` / a plain ``cat | grep`` all
work without a schema migration. Single-writer (one
``session complete`` at a time) avoids concurrency.

The path lives under ``sessions/`` with a leading dot so it does not
show up in ``ls`` of the sessions directory or as a session-id by
the readers that walk that tree.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from tripwire.models.session import AgentSession

_TELEMETRY_FILENAME = ".routing_telemetry.jsonl"


def telemetry_path(project_dir: Path) -> Path:
    """Return the on-disk telemetry log path for ``project_dir``."""
    return project_dir / "sessions" / _TELEMETRY_FILENAME


# ---------- Row schema ---------------------------------------------------


@dataclass
class TelemetryRow:
    """One session-complete row.

    Field order is the on-disk order. Keep it stable: new fields go
    to the end so older analysis scripts don't break.
    """

    sid: str
    task_kind: str | None
    provider: str
    model: str
    effort: str
    merged: bool
    cost_usd: float
    duration_min: int
    re_engages: int
    ci_failures: int

    def as_jsonl_dict(self) -> dict[str, Any]:
        """Serialise the row to a JSONL-friendly dict."""
        return asdict(self)


# ---------- Build a row from a session ------------------------------------


def _spawn_value(session: AgentSession, key: str, default: Any) -> Any:
    """Pull ``key`` from ``session.spawn_config.config``, else default.

    The session model treats spawn_config.config as ``dict[str, Any]``
    today. If KUI-91 promotes ``task_kind`` / ``provider`` to typed
    fields later, this lookup keeps working as long as the dict path
    remains the resolved-config home.
    """
    spawn = session.spawn_config
    if spawn is None:
        return default
    cfg = spawn.config or {}
    val = cfg.get(key)
    if val in (None, ""):
        return default
    return val


def _duration_minutes(session: AgentSession) -> int:
    """Compute total wall-clock duration across engagements, in minutes.

    Uses the first engagement's ``started_at`` and the last
    engagement's ``ended_at``. Falls back to 0 when no engagement has
    closed (session.complete on a still-running session — shouldn't
    happen but the gate is policy, not assertion).
    """
    engagements = session.engagements or []
    if not engagements:
        return 0
    first_started = engagements[0].started_at
    last_ended = engagements[-1].ended_at
    if first_started is None or last_ended is None:
        return 0
    delta = last_ended - first_started
    return int(delta.total_seconds() // 60)


def build_telemetry_row(
    project_dir: Path,
    session: AgentSession,
    *,
    cost_usd: float,
    ci_failures: int = 0,
) -> TelemetryRow:
    """Build a :class:`TelemetryRow` for ``session`` at completion.

    ``cost_usd`` is computed by the caller (so this module can stay
    free of log-file IO) — typically via
    :func:`tripwire.core.session_cost.compute_session_cost`.

    ``ci_failures`` defaults to 0 — the runtime monitor's CI-aware
    exit work (KUI-95) lands the actual count later; until then the
    column is reserved.
    """
    re_engages = max(len(session.engagements) - 1, 0)
    return TelemetryRow(
        sid=session.id,
        task_kind=_spawn_value(session, "task_kind", None),
        provider=_spawn_value(session, "provider", "claude"),
        model=_spawn_value(session, "model", "opus"),
        effort=_spawn_value(session, "effort", "xhigh"),
        merged=True,  # complete_session enforces this gate.
        cost_usd=round(cost_usd, 6),
        duration_min=_duration_minutes(session),
        re_engages=re_engages,
        ci_failures=ci_failures,
    )


# ---------- Append + read ------------------------------------------------


def append_telemetry_row(project_dir: Path, row: TelemetryRow) -> None:
    """Append ``row`` as one JSONL line to the project's telemetry log.

    Creates the file (and ``sessions/`` directory) if needed. Single-
    writer assumption: only ``session complete`` writes here. The file
    is line-oriented — partial writes manifest as a malformed last
    line, which the reader skips.
    """
    path = telemetry_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(row.as_jsonl_dict(), separators=(",", ":"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def read_telemetry(project_dir: Path) -> list[dict[str, Any]]:
    """Return every well-formed row from the telemetry log.

    Missing file → ``[]`` (no sessions completed yet). Malformed
    lines are skipped with no warning — analysis runs across whatever
    is parseable.
    """
    path = telemetry_path(project_dir)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


__all__ = [
    "TelemetryRow",
    "append_telemetry_row",
    "build_telemetry_row",
    "read_telemetry",
    "telemetry_path",
]
