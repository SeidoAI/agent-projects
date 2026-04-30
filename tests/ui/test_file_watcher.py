"""Tests for tripwire.ui.file_watcher — classification, debouncer, handler."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from watchdog.events import (
    DirCreatedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from tripwire.ui.events import FileChangedEvent
from tripwire.ui.file_watcher import (
    Debouncer,
    ProjectFileHandler,
    _should_ignore,
    classify,
    start_watching,
)

# ---------------------------------------------------------------------------
# classify()
# ---------------------------------------------------------------------------


class TestClassify:
    def test_issue(self, tmp_path: Path):
        path = tmp_path / "issues" / "KUI-42" / "issue.yaml"
        ev = classify("p", tmp_path, path, "modified")
        assert isinstance(ev, FileChangedEvent)
        assert ev.entity_type == "issue"
        # entity_id is the directory stem, not the filename (KUI-42 rule).
        assert ev.entity_id == "KUI-42"
        assert ev.path == "issues/KUI-42/issue.yaml"
        assert ev.project_id == "p"

    def test_node(self, tmp_path: Path):
        path = tmp_path / "nodes" / "file-watcher.yaml"
        ev = classify("p", tmp_path, path, "created")
        assert ev is not None
        assert ev.entity_type == "node"
        assert ev.entity_id == "file-watcher"

    def test_session(self, tmp_path: Path):
        path = tmp_path / "sessions" / "backend-realtime" / "session.yaml"
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "session"
        assert ev.entity_id == "backend-realtime"

    def test_session_root_markdown_is_artifact(self, tmp_path: Path):
        path = tmp_path / "sessions" / "backend-realtime" / "plan.md"
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "artifact"
        # entity_id per [[file-watcher]] node: <session>/<name>.
        assert ev.entity_id == "backend-realtime/plan"

    def test_session_artifacts_subdir_is_artifact(self, tmp_path: Path):
        path = (
            tmp_path
            / "sessions"
            / "backend-realtime"
            / "artifacts"
            / "task-checklist.md"
        )
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "artifact"
        assert ev.entity_id == "backend-realtime/task-checklist"

    def test_plans_artifact(self, tmp_path: Path):
        path = tmp_path / "plans" / "artifacts" / "ws-scoping.md"
        ev = classify("p", tmp_path, path, "created")
        assert ev is not None
        assert ev.entity_type == "scoping-artifact"
        assert ev.entity_id == "ws-scoping"

    def test_agent_def(self, tmp_path: Path):
        path = tmp_path / "agents" / "backend-coder.yaml"
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "agent_def"
        assert ev.entity_id == "backend-coder"

    def test_enum(self, tmp_path: Path):
        path = tmp_path / "enums" / "agent_state.yaml"
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "enum"
        assert ev.entity_id == "agent_state"

    def test_project(self, tmp_path: Path):
        path = tmp_path / "project.yaml"
        ev = classify("p", tmp_path, path, "modified")
        assert ev is not None
        assert ev.entity_type == "project"
        assert ev.entity_id == "config"

    def test_unknown_returns_none(self, tmp_path: Path):
        path = tmp_path / "README.md"
        assert classify("p", tmp_path, path, "modified") is None

    def test_path_outside_project_returns_none(self, tmp_path: Path):
        path = tmp_path.parent / "elsewhere" / "project.yaml"
        assert classify("p", tmp_path, path, "modified") is None


# ---------------------------------------------------------------------------
# _should_ignore()
# ---------------------------------------------------------------------------


class TestShouldIgnore:
    def test_git_internal(self, tmp_path: Path):
        assert _should_ignore(tmp_path / ".git" / "refs" / "heads" / "main", tmp_path)

    def test_pycache(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "src" / "__pycache__" / "x.pyc", tmp_path)

    def test_venv(self, tmp_path: Path):
        assert _should_ignore(tmp_path / ".venv" / "bin" / "python", tmp_path)

    def test_claude_dir(self, tmp_path: Path):
        assert _should_ignore(tmp_path / ".claude" / "settings.json", tmp_path)

    def test_ds_store(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "issues" / ".DS_Store", tmp_path)

    def test_swap_file(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "issues" / "x.yaml.swp", tmp_path)

    def test_trailing_tilde(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "issues" / "x.yaml~", tmp_path)

    def test_emacs_lock_file(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "issues" / ".#x.yaml", tmp_path)

    def test_lock_file(self, tmp_path: Path):
        assert _should_ignore(tmp_path / ".tripwire.lock", tmp_path)

    def test_graph_index_self_write(self, tmp_path: Path):
        assert _should_ignore(tmp_path / "graph" / "index.yaml", tmp_path)

    def test_concept_layout_sidecar_ignored(self, tmp_path: Path):
        # The Concept Graph layout sidecar lives at
        # `.tripwire/concept-layout.json`. The whole point of the sidecar
        # design is that layout writes do NOT trigger `file_changed` events
        # — that's what prevents the self-amplifying re-seed loop.
        assert _should_ignore(
            tmp_path / ".tripwire" / "concept-layout.json", tmp_path
        )
        assert _should_ignore(
            tmp_path / ".tripwire" / "concept-layout.json.tmp", tmp_path
        )
        assert _should_ignore(
            tmp_path / ".tripwire" / ".concept-layout.lock", tmp_path
        )

    def test_normal_issue_not_ignored(self, tmp_path: Path):
        assert not _should_ignore(
            tmp_path / "issues" / "KUI-1" / "issue.yaml", tmp_path
        )

    def test_normal_project_yaml_not_ignored(self, tmp_path: Path):
        assert not _should_ignore(tmp_path / "project.yaml", tmp_path)

    def test_path_outside_project_ignored(self, tmp_path: Path):
        other = tmp_path.parent / "other"
        assert _should_ignore(other / "file.txt", tmp_path)


# ---------------------------------------------------------------------------
# Debouncer
# ---------------------------------------------------------------------------


class TestDebouncer:
    def test_burst_collapses_to_one_fire(self):
        d = Debouncer(window_ms=30)
        calls: list[tuple[Any, Any]] = []
        for i in range(10):
            d.schedule("k", i, lambda k, v: calls.append((k, v)))
        time.sleep(0.1)
        assert len(calls) == 1
        # Latest value wins.
        assert calls[0] == ("k", 9)

    def test_independent_keys(self):
        d = Debouncer(window_ms=30)
        calls: list[tuple[Any, Any]] = []
        d.schedule("a", 1, lambda k, v: calls.append((k, v)))
        d.schedule("b", 2, lambda k, v: calls.append((k, v)))
        time.sleep(0.1)
        assert sorted(calls) == [("a", 1), ("b", 2)]

    def test_re_schedule_extends_window(self):
        d = Debouncer(window_ms=40)
        calls: list[Any] = []
        d.schedule("k", 1, lambda k, v: calls.append(v))
        time.sleep(0.02)  # half a window
        d.schedule("k", 2, lambda k, v: calls.append(v))
        time.sleep(0.02)  # still within re-started window
        d.schedule("k", 3, lambda k, v: calls.append(v))
        time.sleep(0.08)  # after the final window elapses
        assert calls == [3]

    def test_cancel_all_stops_pending(self):
        d = Debouncer(window_ms=30)
        calls: list[Any] = []
        d.schedule("k", 1, lambda k, v: calls.append(v))
        d.cancel_all()
        time.sleep(0.06)
        assert calls == []

    def test_callback_exception_does_not_leak(self):
        d = Debouncer(window_ms=15)

        def boom(_k: Any, _v: Any) -> None:
            raise RuntimeError("boom")

        d.schedule("k", 1, boom)
        time.sleep(0.08)
        # Next schedule still works — the debouncer is not wedged.
        calls: list[Any] = []
        d.schedule("k", 2, lambda k, v: calls.append(v))
        time.sleep(0.05)
        assert calls == [2]


# ---------------------------------------------------------------------------
# ProjectFileHandler (unit — synchronous, loop-threadsafe submit)
# ---------------------------------------------------------------------------


@pytest.fixture
def loop_in_thread():
    """Spin up an asyncio loop on a daemon thread; tear it down at teardown."""
    loop = asyncio.new_event_loop()
    ready = threading.Event()

    def run() -> None:
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    ready.wait(timeout=1)
    try:
        yield loop
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        loop.close()


class TestProjectFileHandler:
    def _mkproj(self, tmp_path: Path) -> Path:
        p = tmp_path / "proj"
        p.mkdir()
        (p / "issues" / "KUI-1").mkdir(parents=True)
        return p

    def test_skips_directories(self, tmp_path: Path, loop_in_thread):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        handler.on_any_event(DirCreatedEvent(str(project / "issues" / "KUI-2")))
        time.sleep(0.05)
        assert q.qsize() == 0

    def test_skips_ignored_paths(self, tmp_path: Path, loop_in_thread):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        handler.on_any_event(FileModifiedEvent(str(project / ".git" / "HEAD")))
        handler.on_any_event(FileModifiedEvent(str(project / "graph" / "index.yaml")))
        time.sleep(0.05)
        assert q.qsize() == 0

    def test_classifies_and_enqueues_issue_modify(self, tmp_path: Path, loop_in_thread):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "pid", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        handler.on_any_event(
            FileModifiedEvent(str(project / "issues" / "KUI-1" / "issue.yaml"))
        )
        time.sleep(0.08)

        fut = asyncio.run_coroutine_threadsafe(q.get(), loop_in_thread)
        event = fut.result(timeout=1)
        assert event.entity_type == "issue"
        assert event.entity_id == "KUI-1"
        assert event.action == "modified"
        assert event.project_id == "pid"

    def test_burst_collapses_single_event(self, tmp_path: Path, loop_in_thread):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=40)
        )
        target = project / "issues" / "KUI-1" / "issue.yaml"
        for _ in range(10):
            handler.on_any_event(FileModifiedEvent(str(target)))
        time.sleep(0.15)
        assert q.qsize() == 1

    def test_delete_action(self, tmp_path: Path, loop_in_thread):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        handler.on_any_event(FileDeletedEvent(str(project / "nodes" / "foo.yaml")))
        time.sleep(0.05)
        fut = asyncio.run_coroutine_threadsafe(q.get(), loop_in_thread)
        event = fut.result(timeout=1)
        assert event.action == "deleted"
        assert event.entity_type == "node"
        assert event.entity_id == "foo"

    def test_moved_event_treated_as_modified_on_dest(
        self, tmp_path: Path, loop_in_thread
    ):
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        src = project / "issues" / "KUI-1" / "issue.yaml.tmp"
        dest = project / "issues" / "KUI-1" / "issue.yaml"
        handler.on_any_event(FileMovedEvent(str(src), str(dest)))
        time.sleep(0.05)
        fut = asyncio.run_coroutine_threadsafe(q.get(), loop_in_thread)
        event = fut.result(timeout=1)
        assert event.action == "modified"
        assert event.entity_type == "issue"
        assert event.entity_id == "KUI-1"

    def test_created_is_enqueued_from_timer_thread(
        self, tmp_path: Path, loop_in_thread
    ):
        """Regression: submit must work even though on_any_event fires outside
        the asyncio loop."""
        project = self._mkproj(tmp_path)
        q: asyncio.Queue = asyncio.Queue()
        handler = ProjectFileHandler(
            "p", project, q, loop_in_thread, debouncer=Debouncer(window_ms=15)
        )
        handler.on_any_event(FileCreatedEvent(str(project / "nodes" / "new.yaml")))
        time.sleep(0.05)
        fut = asyncio.run_coroutine_threadsafe(q.get(), loop_in_thread)
        event = fut.result(timeout=1)
        assert event.action == "created"


# ---------------------------------------------------------------------------
# start_watching() end-to-end — real Observer + real filesystem
# ---------------------------------------------------------------------------


class TestStartWatchingE2E:
    def test_touch_file_emits_event(self, tmp_path: Path, loop_in_thread):
        project = tmp_path / "proj"
        (project / "issues" / "KUI-1").mkdir(parents=True)
        q: asyncio.Queue = asyncio.Queue()
        shared = Debouncer(window_ms=40)

        observer = start_watching(
            [("pid", project)], q, loop_in_thread, debouncer=shared
        )
        try:
            time.sleep(0.1)  # let the observer settle
            (project / "issues" / "KUI-1" / "issue.yaml").write_text("x")

            fut = asyncio.run_coroutine_threadsafe(q.get(), loop_in_thread)
            event = fut.result(timeout=2)
            assert event.entity_type == "issue"
            assert event.entity_id == "KUI-1"
            assert event.project_id == "pid"
        finally:
            observer.stop()
            observer.join(timeout=2)
            shared.cancel_all()

    def test_missing_project_dir_is_skipped(self, tmp_path: Path, loop_in_thread):
        q: asyncio.Queue = asyncio.Queue()
        observer = start_watching(
            [("missing", tmp_path / "does-not-exist")], q, loop_in_thread
        )
        try:
            assert observer.is_alive()
        finally:
            observer.stop()
            observer.join(timeout=2)
