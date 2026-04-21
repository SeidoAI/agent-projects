"""Filesystem watcher — turn on-disk project changes into typed events.

A watchdog ``Observer`` runs in its own OS thread and calls the handler's
``on_any_event``. This module classifies each filesystem event to a
:class:`~tripwire.ui.events.FileChangedEvent`, coalesces bursts through a
thread-safe :class:`Debouncer`, and forwards surviving events to the
FastAPI event loop via :func:`asyncio.run_coroutine_threadsafe`.

Classification rules (source of truth):

+-------------------------------+-------------------+
| Path pattern                  | ``entity_type``   |
+===============================+===================+
| ``issues/<KEY>/issue.yaml``   | ``issue``         |
| ``nodes/<id>.yaml``           | ``node``          |
| ``sessions/<id>/session.yaml``| ``session``       |
| ``sessions/<id>/<name>.md``   | ``artifact``      |
| ``sessions/<id>/artifacts/``  | ``artifact``      |
| ``plans/artifacts/*.md``      | ``scoping-artifact`` |
| ``agents/*.yaml``             | ``agent_def``     |
| ``enums/*.yaml``              | ``enum``          |
| ``project.yaml``              | ``project``       |
+-------------------------------+-------------------+

Anything else is silently dropped (debug-logged).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from tripwire.ui.events import FileChangedEvent

logger = logging.getLogger("tripwire.ui.file_watcher")

DEFAULT_DEBOUNCE_MS = 200


# ---------------------------------------------------------------------------
# Ignore list
# ---------------------------------------------------------------------------


_IGNORED_DIR_COMPONENTS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        ".claude",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)

_IGNORED_FILENAMES: frozenset[str] = frozenset({".DS_Store", ".tripwire.lock"})


def _should_ignore(path: Path, project_dir: Path | None = None) -> bool:
    """Return True if *path* matches any known junk/noise pattern.

    The caller should pass *project_dir* so relative components are walked
    (hiding the user's own home-directory dotnames from our filter). When
    omitted, the absolute path parts are used — suitable for unit tests
    where *path* is already project-relative.
    """
    name = path.name

    # Editor/OS junk files by filename.
    if name in _IGNORED_FILENAMES:
        return True
    if name.endswith(".swp") or name.endswith("~"):
        return True
    if name.startswith(".#"):
        return True

    if project_dir is not None:
        try:
            rel_parts = path.relative_to(project_dir).parts
        except ValueError:
            # Outside the project tree — refuse to classify.
            return True
    else:
        rel_parts = path.parts

    # Self-written graph cache — must be skipped or we get infinite event loops.
    if rel_parts == ("graph", "index.yaml"):
        return True

    for part in rel_parts:
        if part in _IGNORED_DIR_COMPONENTS:
            return True
        if part.startswith("."):
            return True

    return False


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify(
    project_id: str,
    project_dir: Path,
    path: Path,
    action: str,
) -> FileChangedEvent | None:
    """Classify *path* under *project_dir* into a FileChangedEvent.

    Returns ``None`` for paths that do not match any known entity pattern
    (these are logged at DEBUG and dropped). *action* must be one of
    ``"created"``, ``"modified"``, ``"deleted"``.
    """
    try:
        rel = path.relative_to(project_dir)
    except ValueError:
        return None

    parts = rel.parts
    rel_posix = rel.as_posix()
    stem = path.stem
    suffix = path.suffix

    # project.yaml at the root
    if rel_posix == "project.yaml":
        return _event(project_id, "project", "config", action, rel_posix)

    # issues/<KEY>/issue.yaml
    if len(parts) == 3 and parts[0] == "issues" and parts[2] == "issue.yaml":
        return _event(project_id, "issue", parts[1], action, rel_posix)

    # nodes/<id>.yaml
    if len(parts) == 2 and parts[0] == "nodes" and suffix == ".yaml":
        return _event(project_id, "node", stem, action, rel_posix)

    # sessions/<id>/session.yaml
    if len(parts) == 3 and parts[0] == "sessions" and parts[2] == "session.yaml":
        return _event(project_id, "session", parts[1], action, rel_posix)

    # sessions/<id>/<name>.md   (plan, task-checklist, etc. at session root).
    # entity_id is "<session>/<name>" per the [[file-watcher]] node so the
    # frontend can invalidate per-artifact queries, not the whole session.
    if len(parts) == 3 and parts[0] == "sessions" and suffix == ".md":
        return _event(project_id, "artifact", f"{parts[1]}/{stem}", action, rel_posix)

    # sessions/<id>/artifacts/<name>.md
    if (
        len(parts) == 4
        and parts[0] == "sessions"
        and parts[2] == "artifacts"
        and suffix == ".md"
    ):
        return _event(project_id, "artifact", f"{parts[1]}/{stem}", action, rel_posix)

    # plans/artifacts/<name>.md
    if (
        len(parts) == 3
        and parts[0] == "plans"
        and parts[1] == "artifacts"
        and suffix == ".md"
    ):
        return _event(project_id, "scoping-artifact", stem, action, rel_posix)

    # agents/<id>.yaml
    if len(parts) == 2 and parts[0] == "agents" and suffix == ".yaml":
        return _event(project_id, "agent_def", stem, action, rel_posix)

    # enums/<id>.yaml
    if len(parts) == 2 and parts[0] == "enums" and suffix == ".yaml":
        return _event(project_id, "enum", stem, action, rel_posix)

    return None


def _event(
    project_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    rel_posix: str,
) -> FileChangedEvent:
    return FileChangedEvent(
        project_id=project_id,
        entity_type=entity_type,  # type: ignore[arg-type]
        entity_id=entity_id,
        action=action,  # type: ignore[arg-type]
        path=rel_posix,
    )


# ---------------------------------------------------------------------------
# Debouncer
# ---------------------------------------------------------------------------


class Debouncer:
    """Thread-safe per-key debouncer.

    ``schedule(key, value, callback)`` restarts the timer for *key*; when
    the window elapses with no further ``schedule()`` call for that key,
    *callback* fires once with the last-seen value. Timers run on daemon
    threads so process shutdown does not block on them.
    """

    def __init__(self, window_ms: int = DEFAULT_DEBOUNCE_MS) -> None:
        self._window = window_ms / 1000.0
        self._lock = threading.Lock()
        self._timers: dict[Any, threading.Timer] = {}
        self._pending: dict[Any, Any] = {}

    def schedule(
        self,
        key: Any,
        value: Any,
        callback: Callable[[Any, Any], None],
    ) -> None:
        with self._lock:
            existing = self._timers.pop(key, None)
            if existing is not None:
                existing.cancel()
            self._pending[key] = value
            timer = threading.Timer(self._window, self._fire, args=(key, callback))
            timer.daemon = True
            self._timers[key] = timer
            timer.start()

    def _fire(self, key: Any, callback: Callable[[Any, Any], None]) -> None:
        with self._lock:
            self._timers.pop(key, None)
            value = self._pending.pop(key, None)
        if value is None:
            return
        try:
            callback(key, value)
        except Exception:
            logger.exception("debouncer callback failed for key=%r", key)

    def cancel_all(self) -> None:
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
            self._pending.clear()

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


# ---------------------------------------------------------------------------
# watchdog handler
# ---------------------------------------------------------------------------


_WATCHDOG_ACTION_MAP: dict[str, str] = {
    "created": "created",
    "modified": "modified",
    "deleted": "deleted",
}


class ProjectFileHandler(FileSystemEventHandler):
    """watchdog handler: classify → debounce → submit to the asyncio queue."""

    def __init__(
        self,
        project_id: str,
        project_dir: Path,
        queue: asyncio.Queue[FileChangedEvent],
        loop: asyncio.AbstractEventLoop,
        *,
        debouncer: Debouncer | None = None,
    ) -> None:
        super().__init__()
        self.project_id = project_id
        self.project_dir = Path(project_dir)
        self.queue = queue
        self.loop = loop
        self.debouncer = debouncer or Debouncer()

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return

        event_type = event.event_type
        if event_type == "moved":
            raw_path = getattr(event, "dest_path", None) or event.src_path
            action = "modified"
        else:
            action = _WATCHDOG_ACTION_MAP.get(event_type, "")
            if not action:
                return
            raw_path = event.src_path

        path = Path(raw_path)
        if _should_ignore(path, self.project_dir):
            return

        classified = classify(self.project_id, self.project_dir, path, action)
        if classified is None:
            # Per KUI-36 execution constraint: unclassified paths log-and-skip,
            # never raise.
            logger.debug("unclassified fs event: %s (action=%s)", path, action)
            return

        key = (self.project_id, classified.entity_type, classified.entity_id)
        self.debouncer.schedule(key, classified, self._dispatch)

    def _dispatch(self, key: Any, event: FileChangedEvent) -> None:
        """Forward *event* onto the asyncio queue from a Timer thread."""
        if self.loop.is_closed():
            return
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(event), self.loop)
        except RuntimeError:
            # Loop not running — expected during lifespan shutdown.
            logger.debug("dropped event for key=%r: loop not running", key)


# ---------------------------------------------------------------------------
# Observer lifecycle
# ---------------------------------------------------------------------------


def start_watching(
    project_dirs: list[tuple[str, Path]],
    queue: asyncio.Queue[FileChangedEvent],
    loop: asyncio.AbstractEventLoop,
    *,
    debouncer: Debouncer | None = None,
) -> BaseObserver:
    """Start a watchdog ``Observer`` scheduling a handler per project.

    The caller owns the returned observer — call ``observer.stop()`` +
    ``observer.join()`` on shutdown (the FastAPI lifespan does this).
    A directory that fails to schedule is logged and skipped; the observer
    continues with the remaining projects.
    """
    shared_debouncer = debouncer or Debouncer()
    observer: BaseObserver = Observer()

    for project_id, raw_dir in project_dirs:
        project_dir = Path(raw_dir).resolve()
        if not project_dir.is_dir():
            logger.warning("skipping watcher for %s — not a directory", project_dir)
            continue
        handler = ProjectFileHandler(
            project_id=project_id,
            project_dir=project_dir,
            queue=queue,
            loop=loop,
            debouncer=shared_debouncer,
        )
        try:
            observer.schedule(handler, str(project_dir), recursive=True)
        except Exception:
            logger.exception("failed to schedule watcher for %s", project_dir)
            continue

    observer.start()
    return observer


__all__ = [
    "DEFAULT_DEBOUNCE_MS",
    "Debouncer",
    "ProjectFileHandler",
    "classify",
    "start_watching",
]
