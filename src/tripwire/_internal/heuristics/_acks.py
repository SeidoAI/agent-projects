"""Marker file machinery for heuristic suppression.

A heuristic ``v_*`` fires once per ``(heuristic_id, entity_uuid,
condition_hash)`` triple. The marker is the disk witness of "the agent
saw this and chose not to act." When the underlying evidence changes,
``condition_hash`` differs, the existing marker no longer matches, and
the heuristic re-fires. No timestamp-based decay; staleness is
content-driven.

Marker layout::

    .tripwire/heuristic-acks/
      <heuristic-id>/
        <entity-uuid>-<condition-hash>.json

Each JSON payload records ``{first_fired_at, last_seen_at,
evidence_summary}``. ``last_seen_at`` is updated by the suppression
caller; ``first_fired_at`` stays pinned at first-fire time.

GC removes markers whose entity_uuid no longer resolves to a live entity
(deleted issues/nodes/sessions). The ``project`` pseudo-entity (for
project-singleton heuristics like sequence_drift) is always live.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ACK_DIR_REL = ".tripwire/heuristic-acks"
PROJECT_SINGLETON_UUID = "project"


@dataclass(frozen=True)
class MarkerKey:
    """Identifies a single heuristic suppression marker."""

    heuristic_id: str
    entity_uuid: str
    condition_hash: str


def condition_hash(*parts: str) -> str:
    """Deterministic short hash of the heuristic's evidence inputs.

    Caller decides what counts as evidence (typically: check code,
    message body, file path, line). The hash is short (12 chars) — long
    enough to avoid accidental collisions across the few-thousand-finding
    scale but short enough to keep marker filenames readable.
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return digest[:12]


def marker_path(project_dir: Path, key: MarkerKey) -> Path:
    """Return the absolute path to a marker file."""
    return (
        project_dir
        / ACK_DIR_REL
        / key.heuristic_id
        / f"{key.entity_uuid}-{key.condition_hash}.json"
    )


def has_marker(project_dir: Path, key: MarkerKey) -> bool:
    """Return True iff a marker file exists for this key."""
    return marker_path(project_dir, key).is_file()


def write_marker(
    project_dir: Path,
    key: MarkerKey,
    *,
    evidence_summary: str = "",
) -> Path:
    """Create or refresh a marker.

    First write pins ``first_fired_at`` to now. Subsequent writes only
    bump ``last_seen_at`` and refresh ``evidence_summary``; this is how
    the suppression caller signals "the agent ran past this again."
    """
    path = marker_path(project_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(tz=timezone.utc).isoformat()
    payload: dict[str, str] = {}
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload.update({k: v for k, v in existing.items() if isinstance(v, str)})
        except (OSError, json.JSONDecodeError):
            pass
    payload.setdefault("first_fired_at", now)
    payload["last_seen_at"] = now
    if evidence_summary:
        payload["evidence_summary"] = evidence_summary
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def reset_markers(
    project_dir: Path,
    *,
    heuristic_id: str | None = None,
    entity_uuid: str | None = None,
) -> int:
    """Delete markers matching the given filters.

    Returns the count removed. ``heuristic_id=None`` means all
    heuristics; ``entity_uuid=None`` means all entities for the chosen
    heuristic(s). Empty directories left behind are cleaned up.
    """
    root = project_dir / ACK_DIR_REL
    if not root.is_dir():
        return 0

    targets = (
        [root / heuristic_id] if heuristic_id is not None else list(root.iterdir())
    )
    removed = 0
    for hd in targets:
        if not hd.is_dir():
            continue
        for marker in hd.glob("*.json"):
            if entity_uuid is not None and not marker.name.startswith(
                f"{entity_uuid}-"
            ):
                continue
            try:
                marker.unlink()
                removed += 1
            except OSError:
                continue
        # Sweep empty directories.
        try:
            if not any(hd.iterdir()):
                hd.rmdir()
        except OSError:
            pass
    return removed


def gc_markers(project_dir: Path, live_uuids: set[str]) -> int:
    """Remove markers whose entity_uuid no longer points at a live entity.

    ``live_uuids`` is the set of entity UUIDs the caller considers
    current (issues + sessions + nodes). The ``project`` singleton is
    always preserved.
    Returns the count removed.
    """
    root = project_dir / ACK_DIR_REL
    if not root.is_dir():
        return 0

    keep = set(live_uuids) | {PROJECT_SINGLETON_UUID}
    removed = 0
    for hd in root.iterdir():
        if not hd.is_dir():
            continue
        for marker in hd.glob("*.json"):
            stem = marker.stem  # "<entity-uuid>-<hash>"
            entity = stem.rsplit("-", 1)[0] if "-" in stem else stem
            if entity in keep:
                continue
            try:
                marker.unlink()
                removed += 1
            except OSError:
                continue
        try:
            if not any(hd.iterdir()):
                hd.rmdir()
        except OSError:
            pass
    return removed


__all__ = [
    "ACK_DIR_REL",
    "PROJECT_SINGLETON_UUID",
    "MarkerKey",
    "condition_hash",
    "gc_markers",
    "has_marker",
    "marker_path",
    "reset_markers",
    "write_marker",
]
