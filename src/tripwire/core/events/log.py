"""Append-only workflow events log writer + reader (KUI-123).

Layout: ``<project>/events/<YYYY-MM-DD>.jsonl`` (UTC date, one JSON
record per line). Append-forever — no rotation in v0.9 (locked
decision in ``backlog-architecture.md``: file-size becomes a v1.0
housekeeping question if it ever does).

Concurrency: appends are serialised per-day-file with the
:class:`tripwire.core.locks.project_lock` cross-process advisory lock
on a per-day key — different days proceed in parallel, same-day
appends queue. The append itself is one ``open(..., 'a')`` write,
which is atomic on POSIX up to PIPE_BUF; we don't truncate or rewrite,
so a crash mid-write at most leaves a partial trailing line that the
reader skips (json.loads raises, we filter).

All emission goes via :func:`emit_event`. Three callers:

- :mod:`tripwire.core.validator` (KUI-120) — emits ``validator.run``
  per check function as part of every ``tripwire validate`` run.
- :mod:`tripwire._internal.tripwires` (KUI-121) — emits
  ``tripwire.fired`` when a tripwire fires.
- :mod:`tripwire.core.workflow.transitions` (KUI-159) — emits
  ``transition.requested`` / ``transition.completed`` /
  ``transition.rejected`` for each gate run.

The drift detector (KUI-124) consumes via :func:`read_events`.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tripwire.core.events.schema import Event
from tripwire.core.locks import project_lock

EVENTS_DIRNAME = "events"


def events_dir(project_dir: Path) -> Path:
    return project_dir / EVENTS_DIRNAME


def _isoformat_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_filename(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"


def emit_event(
    project_dir: Path,
    *,
    workflow: str,
    instance: str,
    station: str,
    event: str,
    details: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Event:
    """Append one event to ``<project>/events/<UTC-date>.jsonl``.

    ``now`` is exposed for testability — production callers always
    pass ``None`` and pick up the current time. Returns the
    :class:`Event` written so callers can chain logging or assertions.

    Empty ``workflow`` / ``event`` / ``instance`` / ``station`` strings
    raise :class:`ValueError` — the schema demands them.
    """
    if not workflow:
        raise ValueError("workflow must be a non-empty string")
    if not instance:
        raise ValueError("instance must be a non-empty string")
    if not station:
        raise ValueError("station must be a non-empty string")
    if not event:
        raise ValueError("event must be a non-empty string")

    when = now or datetime.now(tz=timezone.utc)
    record = Event(
        ts=_isoformat_z(when),
        workflow=workflow,
        instance=instance,
        station=station,
        event=event,
        details=dict(details or {}),
    )

    target_dir = events_dir(project_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / _today_filename(when)

    line = json.dumps(record.to_json(), ensure_ascii=False, sort_keys=False)
    lock_name = f"{EVENTS_DIRNAME}/.{target.name}.lock"
    with project_lock(project_dir, name=lock_name):
        with target.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.write("\n")
    return record


def read_events(
    project_dir: Path,
    *,
    workflow: str | None = None,
    instance: str | None = None,
    station: str | None = None,
    event: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield events matching the given filters in chronological order.

    Multiple files (one per day) are concatenated in filename order
    (lexicographic sort = chronological because the format is
    ``YYYY-MM-DD``). A missing ``events/`` directory yields nothing.

    Returns plain dicts (the JSON shape) rather than :class:`Event`
    instances — callers that want typed access can pass through
    :meth:`Event.from_json`.
    """
    target_dir = events_dir(project_dir)
    if not target_dir.is_dir():
        return
    for path in sorted(target_dir.glob("*.jsonl")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                # Tolerate a partial last line from a crashed write.
                continue
            if not isinstance(payload, dict):
                continue
            if workflow is not None and payload.get("workflow") != workflow:
                continue
            if instance is not None and payload.get("instance") != instance:
                continue
            if station is not None and payload.get("station") != station:
                continue
            if event is not None and payload.get("event") != event:
                continue
            yield payload


__all__ = ["EVENTS_DIRNAME", "emit_event", "events_dir", "read_events"]
