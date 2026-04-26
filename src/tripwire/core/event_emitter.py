"""Event-emission abstractions used by tripwire's process-event channel.

Subsystems (validators, the tripwire registry, artifact-approval, pm_reviews,
session_store) call `EventEmitter.emit(kind, payload)` at the moment of an
action. The default `NullEmitter` is a no-op and keeps batch / unit-test
behaviour unchanged. The `FileEmitter` writes a JSON record to
`<project_dir>/.tripwire/events/<kind>/<sid>/<n>.json`, where `<sid>` is the
`session_id` field of the payload and `<n>` is a per-(kind, sid) monotonic
4-digit-padded integer.

The on-disk layout is the contract consumed by `ui/file_watcher.py`
(broadcasts `process_event` to WS clients on each new file) and by
`/api/events` aggregation (globs across kind subdirs). See
`docs/specs/2026-04-26-v08-handoff.md` §1.2, §2.2, §4.16.

Concurrency: per-(kind, sid) allocation of `<n>` is serialised with
`fcntl.flock` via `tripwire.core.locks.project_lock`. The lock file lives at
`<project_dir>/.tripwire/events/<kind>/<sid>/.lock`, so concurrent emits to
*different* (kind, sid) pairs proceed in parallel. The actual file write
goes through a temp file + atomic rename so a crash mid-write never leaves
a partial JSON record on disk.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from tripwire.core.locks import project_lock

EVENTS_REL_DIR = ".tripwire/events"
EVENT_FILENAME_RE = re.compile(r"^(\d+)\.json$")
PAD_WIDTH = 4


@runtime_checkable
class EventEmitter(Protocol):
    """Emits a process-event record.

    Implementations must be callable by any subsystem at the moment of an
    action; they may be no-ops (`NullEmitter`) or persist to disk
    (`FileEmitter`). Returns the absolute path written, or the empty string
    if no file was produced.
    """

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str: ...


class NullEmitter:
    """No-op emitter. Used in batch / unit-test contexts where existing
    behaviour must be preserved."""

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str:
        return ""


class FileEmitter:
    """Persists events to `<project_dir>/.tripwire/events/<kind>/<sid>/<n>.json`."""

    def __init__(self, project_dir: Path | str) -> None:
        self.project_dir = Path(project_dir)

    def emit(self, kind: str, payload: Mapping[str, Any]) -> str:
        _validate_kind(kind)
        sid = _extract_session_id(payload)

        events_dir = self.project_dir / EVENTS_REL_DIR / kind / sid
        events_dir.mkdir(parents=True, exist_ok=True)

        # Lock per (kind, sid) so different sessions / kinds don't serialise.
        lock_name = f"{EVENTS_REL_DIR}/{kind}/{sid}/.lock"
        with project_lock(self.project_dir, name=lock_name):
            n = _next_index(events_dir)
            target = events_dir / f"{n:0{PAD_WIDTH}d}.json"
            tmp = target.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=False),
                encoding="utf-8",
            )
            os.replace(tmp, target)

        return str(target)


def _validate_kind(kind: str) -> None:
    if not kind:
        raise ValueError("kind must be a non-empty string")
    if "/" in kind or "\\" in kind or kind in {".", ".."}:
        raise ValueError(f"kind must not contain path separators: {kind!r}")


def _extract_session_id(payload: Mapping[str, Any]) -> str:
    sid = payload.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise ValueError("payload must contain a non-empty 'session_id' string")
    if "/" in sid or "\\" in sid or sid in {".", ".."}:
        raise ValueError(f"session_id must not contain path separators: {sid!r}")
    return sid


def _next_index(events_dir: Path) -> int:
    """Return the next free monotonic index for `events_dir`.

    Scans existing `<digits>.json` files and returns max + 1, or 1 if none
    exist. Caller must hold the per-(kind, sid) lock.
    """
    highest = 0
    for entry in events_dir.iterdir():
        if not entry.is_file():
            continue
        m = EVENT_FILENAME_RE.match(entry.name)
        if m is None:
            continue
        n = int(m.group(1))
        if n > highest:
            highest = n
    return highest + 1
