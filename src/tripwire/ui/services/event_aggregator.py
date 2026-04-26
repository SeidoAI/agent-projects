"""Read-side aggregation of `.tripwire/events/<kind>/<sid>/<n>.json`.

The producer side (`tripwire.core.event_emitter.FileEmitter`) writes one
JSON per event under a fixed `<kind>/<sid>/<n>.json` layout. This module
reads those files back, sorts newest-first across kinds, optionally
filters, and paginates by cursor for the `/api/events` route.

Event IDs surfaced through `/api/events` and `/api/events/<id>` use a
synthetic encoding that captures the on-disk location. The producer-set
`id` field inside the JSON body is preserved verbatim in responses, but
this module's URL-safe id (encoded by `encode_event_id`) is what callers
use to look up a single event because it tells us which file to open
without scanning every kind dir again. See
`docs/specs/2026-04-26-v08-handoff.md` §2.2–§2.3.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EVENTS_REL_DIR = ".tripwire/events"
EVENT_FILENAME_RE = re.compile(r"^(\d+)\.json$")
ENCODED_ID_RE = re.compile(r"^([A-Za-z0-9_]+)/([^/]+)/(\d+)$")
KIND_RE = re.compile(r"^[A-Za-z0-9_]+$")
SID_RE = re.compile(r"^[A-Za-z0-9._-][A-Za-z0-9._-]*$")

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


class EventNotFoundError(LookupError):
    """Raised when `get_event` cannot resolve an encoded id to a file."""


@dataclass(frozen=True)
class EventPage:
    """One page of `/api/events`."""

    events: list[dict[str, Any]]
    next_cursor: str | None


@dataclass(frozen=True)
class _EventRef:
    """Pointer to one event file with the sort keys we need.

    Sorting by `(fired_at, kind, sid, n)` is total — `fired_at` resolves
    most ties, but two emits within the same wall-clock second still need
    a deterministic order, so the on-disk path tuple breaks any remaining
    ties. The composite cursor below uses the same tuple.
    """

    fired_at: str
    kind: str
    session_id: str
    n: int
    path: Path


def encode_event_id(kind: str, session_id: str, n: int) -> str:
    """Produce the URL-safe id used by `/api/events/<id>`.

    The format is `<kind>/<sid>/<n>`. `n` is the integer index, not the
    zero-padded filename — callers pass the literal index, this function
    handles the rest.
    """
    return f"{kind}/{session_id}/{n}"


def _decode_event_id(encoded: str) -> tuple[str, str, int] | None:
    """Inverse of `encode_event_id`. Returns ``None`` for malformed input.

    Validates against the `kind` / `session_id` charsets the emitter uses
    so a hostile id like `firings/../escape/1` cannot reach disk.
    """
    m = ENCODED_ID_RE.match(encoded)
    if m is None:
        return None
    kind, sid, n_str = m.group(1), m.group(2), m.group(3)
    if not KIND_RE.match(kind) or not SID_RE.match(sid):
        return None
    if sid in {".", ".."}:
        return None
    return kind, sid, int(n_str)


def _events_root(project_dir: Path) -> Path:
    return project_dir / EVENTS_REL_DIR


def _iter_refs(project_dir: Path) -> list[_EventRef]:
    """Walk the events tree once and return one `_EventRef` per file.

    Files that aren't JSON or don't carry a `fired_at` string are
    silently skipped — the aggregator must remain robust to in-flight
    writes (`*.tmp`) and partially-corrupt records.
    """
    root = _events_root(project_dir)
    if not root.is_dir():
        return []

    refs: list[_EventRef] = []
    for kind_dir in root.iterdir():
        if not kind_dir.is_dir() or not KIND_RE.match(kind_dir.name):
            continue
        kind = kind_dir.name
        for sid_dir in kind_dir.iterdir():
            if not sid_dir.is_dir():
                continue
            sid = sid_dir.name
            for entry in sid_dir.iterdir():
                if not entry.is_file():
                    continue
                m = EVENT_FILENAME_RE.match(entry.name)
                if m is None:
                    continue
                n = int(m.group(1))
                fired_at = _read_fired_at(entry)
                if fired_at is None:
                    continue
                refs.append(
                    _EventRef(
                        fired_at=fired_at,
                        kind=kind,
                        session_id=sid,
                        n=n,
                        path=entry,
                    )
                )
    return refs


def _read_fired_at(path: Path) -> str | None:
    """Pull `fired_at` from a JSON file without raising on bad input."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("event_aggregator: skipping unreadable %s", path)
        return None
    fired_at = body.get("fired_at")
    return fired_at if isinstance(fired_at, str) and fired_at else None


def _sort_key(ref: _EventRef) -> tuple[str, str, str, int]:
    """Total ordering key, descending sort produces newest-first."""
    return (ref.fired_at, ref.kind, ref.session_id, ref.n)


def _ref_sort_value(ref: _EventRef) -> str:
    """Composite cursor value — encodes the full sort tuple."""
    return f"{ref.fired_at}|{ref.kind}|{ref.session_id}|{ref.n:010d}"


def _cursor_value(ref: _EventRef) -> str:
    """Cursor surfaced to clients — same shape as `_ref_sort_value`.

    A future migration could base64-encode this; for now it's plain
    enough that test failures are debuggable from the response body.
    """
    return _ref_sort_value(ref)


def list_events(
    project_dir: Path,
    *,
    session_id: str | None = None,
    kinds: list[str] | None = None,
    since: str | None = None,
    limit: int = DEFAULT_LIMIT,
    cursor: str | None = None,
) -> EventPage:
    """Return one paginated, filtered, newest-first page of events.

    Filters compose: `session_id` AND `kinds` AND `since` (lexicographic
    string compare on ISO-8601 timestamps). `limit` is clamped to the
    inclusive range `[1, MAX_LIMIT]`. `cursor` is opaque — callers pass
    the value from the previous page's `next_cursor`.
    """
    if limit < 1:
        limit = 1
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    refs = _iter_refs(project_dir)

    if session_id is not None:
        refs = [r for r in refs if r.session_id == session_id]
    if kinds:
        kind_set = set(kinds)
        # Refs are keyed by directory kind (`firings`/`validator_runs`/…),
        # but callers filter by event kind (`tripwire_fire`/…). The
        # mapping is stored *inside* each event body, so consult the file
        # only when a kind filter is in play.
        refs = [r for r in refs if _read_event_kind(r.path) in kind_set]
    if since is not None:
        refs = [r for r in refs if r.fired_at > since]

    refs.sort(key=_sort_key, reverse=True)

    if cursor is not None:
        refs = [r for r in refs if _ref_sort_value(r) < cursor]

    page = refs[:limit]
    next_cursor: str | None = None
    if len(refs) > limit:
        next_cursor = _cursor_value(page[-1])

    bodies: list[dict[str, Any]] = []
    for ref in page:
        body = _read_body(ref.path)
        if body is None:
            continue
        bodies.append(body)

    return EventPage(events=bodies, next_cursor=next_cursor)


def _read_event_kind(path: Path) -> str | None:
    """Return the body's `kind` field — used by the kind filter."""
    body = _read_body(path)
    if body is None:
        return None
    kind = body.get("kind")
    return kind if isinstance(kind, str) else None


def _read_body(path: Path) -> dict[str, Any] | None:
    """Load and return the full JSON body, or `None` on read/parse failure."""
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("event_aggregator: dropping unreadable %s", path)
        return None
    if not isinstance(body, dict):
        return None
    return body


def get_event(project_dir: Path, encoded_id: str) -> dict[str, Any]:
    """Return the full event body for `encoded_id`.

    Raises:
        EventNotFoundError: id is malformed, escapes the events root, or
            references a missing file.
    """
    parts = _decode_event_id(encoded_id)
    if parts is None:
        raise EventNotFoundError(f"Malformed event id: {encoded_id!r}")
    kind, sid, n = parts

    root = _events_root(project_dir).resolve()
    candidate = (root / kind / sid / f"{n:04d}.json").resolve()

    try:
        candidate.relative_to(root)
    except ValueError as exc:  # path traversal guard
        raise EventNotFoundError(
            f"Event id escapes events root: {encoded_id!r}"
        ) from exc

    if not candidate.is_file():
        raise EventNotFoundError(f"Event not found: {encoded_id!r}")

    body = _read_body(candidate)
    if body is None:
        raise EventNotFoundError(f"Event unreadable: {encoded_id!r}")
    return body


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "EventNotFoundError",
    "EventPage",
    "encode_event_id",
    "get_event",
    "list_events",
]
