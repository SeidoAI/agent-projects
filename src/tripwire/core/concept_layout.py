"""Project-scoped Concept Graph layout sidecar.

The Concept Graph view (KUI-104) seeds canvas positions with d3-force on
first load and persists the resting `(x, y)` of each node. Earlier
revisions stored these on the node YAML itself (`nodes/<id>.yaml :: layout`),
which routed every position update through the watchdog, classified it as
a node change, and fanned out `file_changed` events that reinvalidated the
graph and triggered a self-amplifying re-seed loop.

Display coordinates are UI state, not project state. They live here, in
`.tripwire/concept-layout.json`, which the file watcher ignores
(`ui/file_watcher._should_ignore` filters everything under `.tripwire/`
except `events/`). One batched write per debounced flush, no fan-out.

Schema::

    {
      "version": 1,
      "layouts": {
        "<node-id>": {"x": <float>, "y": <float>}
      }
    }

Atomic writes use the same tmp-file + rename + `flock` pattern as
`core/graph/cache.py` so concurrent merges don't corrupt the file.
"""

from __future__ import annotations

import fcntl
import json
import logging
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from tripwire.core import paths

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

DEFAULT_LOCK_TIMEOUT_S = 10.0
LOCK_POLL_INTERVAL_S = 0.05


# ---------------------------------------------------------------------------
# Locking
# ---------------------------------------------------------------------------


@contextmanager
def _layout_lock(
    project_dir: Path, timeout_s: float = DEFAULT_LOCK_TIMEOUT_S
) -> Iterator[None]:
    """Acquire an exclusive `flock` on the layout sidecar's lock file."""
    lock_path = paths.concept_layout_lock_path(project_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)

    deadline = time.monotonic() + timeout_s
    with lock_path.open("a") as fh:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Could not acquire lock {lock_path} within {timeout_s}s."
                    ) from None
                time.sleep(LOCK_POLL_INTERVAL_S)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


# ---------------------------------------------------------------------------
# Load / save
# ---------------------------------------------------------------------------


def load_concept_layouts(project_dir: Path) -> dict[str, tuple[float, float]]:
    """Read the sidecar; return `{}` on missing, corrupt, or version-mismatched.

    A corrupt sidecar is recoverable: the next d3-force pass re-seeds and
    a subsequent PATCH overwrites it.
    """
    path = paths.concept_layout_path(project_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    if raw.get("version") != SCHEMA_VERSION:
        return {}
    layouts_raw = raw.get("layouts")
    if not isinstance(layouts_raw, dict):
        return {}
    out: dict[str, tuple[float, float]] = {}
    for node_id, entry in layouts_raw.items():
        if not isinstance(node_id, str):
            continue
        if not isinstance(entry, dict):
            continue
        x = entry.get("x")
        y = entry.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            continue
        out[node_id] = (float(x), float(y))
    return out


def _write_atomic(path: Path, layouts: Mapping[str, tuple[float, float]]) -> None:
    """Tmp-file + rename so partial writes never leave a corrupt sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    payload = {
        "version": SCHEMA_VERSION,
        "layouts": {nid: {"x": x, "y": y} for nid, (x, y) in layouts.items()},
    }
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp.replace(path)


def save_concept_layouts(
    project_dir: Path, layouts: Mapping[str, tuple[float, float]]
) -> None:
    """Replace the sidecar's layouts with *layouts* atomically."""
    path = paths.concept_layout_path(project_dir)
    with _layout_lock(project_dir):
        _write_atomic(path, layouts)


def merge_concept_layouts(
    project_dir: Path, updates: Mapping[str, tuple[float, float]]
) -> dict[str, tuple[float, float]]:
    """Merge *updates* into the existing sidecar and return the result.

    The read-modify-write happens under the same lock so concurrent flushes
    don't drop entries.
    """
    path = paths.concept_layout_path(project_dir)
    with _layout_lock(project_dir):
        # Inline a lock-free read so we don't recurse on the lock.
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                existing_raw = (
                    raw.get("layouts")
                    if isinstance(raw, dict) and raw.get("version") == SCHEMA_VERSION
                    else None
                )
            except (OSError, json.JSONDecodeError):
                existing_raw = None
        else:
            existing_raw = None

        merged: dict[str, tuple[float, float]] = {}
        if isinstance(existing_raw, dict):
            for nid, entry in existing_raw.items():
                if not isinstance(nid, str) or not isinstance(entry, dict):
                    continue
                x, y = entry.get("x"), entry.get("y")
                if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                    merged[nid] = (float(x), float(y))
        for nid, (x, y) in updates.items():
            merged[nid] = (float(x), float(y))

        _write_atomic(path, merged)
        return merged


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def bootstrap_from_yaml_if_absent(project_dir: Path) -> None:
    """Lift any pre-refactor `node.layout` values into the sidecar.

    Runs once per project: if the sidecar is already on disk, this is a
    no-op. If absent, scan `nodes/*.yaml`, copy any `layout: {x, y}` field
    into the sidecar, and write atomically. The YAMLs are *not* rewritten —
    that would fan `file_changed` events and reproduce the loop this
    refactor exists to fix. The orphan YAML key is harmless; nothing reads
    it after this point.
    """
    path = paths.concept_layout_path(project_dir)
    if path.exists():
        return
    if not paths.nodes_dir(project_dir).is_dir():
        # Nothing to migrate; still create an empty sidecar so subsequent
        # calls short-circuit on the existence check above.
        save_concept_layouts(project_dir, {})
        return

    # Imported lazily to avoid a top-level cycle: node_store imports paths,
    # which imports nothing else from core.
    from tripwire.core.node_store import list_nodes

    lifted: dict[str, tuple[float, float]] = {}
    try:
        for node in list_nodes(project_dir):
            layout = getattr(node, "layout", None)
            if layout is None:
                continue
            lifted[node.id] = (float(layout.x), float(layout.y))
    except (OSError, ValueError) as exc:
        # A malformed YAML shouldn't block the bootstrap; skip and move on.
        logger.warning("concept_layout: bootstrap could not read all nodes: %s", exc)

    save_concept_layouts(project_dir, lifted)


__all__ = [
    "SCHEMA_VERSION",
    "bootstrap_from_yaml_if_absent",
    "load_concept_layouts",
    "merge_concept_layouts",
    "save_concept_layouts",
]
