"""Tests for the `.tripwire/events/` extension to file_watcher.

KUI-100 — see `docs/specs/2026-04-26-v08-handoff.md` §2.4. Files written
by `FileEmitter` under `.tripwire/events/<kind>/<sid>/<n>.json` must be
classified as a `ProcessEvent` and broadcast on the WS hub. Without this
extension the existing dot-prefix filter would silently drop them.
"""

from __future__ import annotations

from pathlib import Path

from tripwire.ui.events import ProcessEvent
from tripwire.ui.file_watcher import _should_ignore, classify_process_event


def test_should_not_ignore_event_files(tmp_path: Path) -> None:
    """Event files MUST survive the ignore filter even though `.tripwire/`
    starts with a dot — the rest of `.tripwire/` (locks, cache files,
    etc.) still gets ignored, but `events/` is whitelisted."""
    event_path = tmp_path / ".tripwire" / "events" / "firings" / "s1" / "0001.json"
    assert _should_ignore(event_path, tmp_path) is False


def test_should_still_ignore_other_dot_tripwire_paths(tmp_path: Path) -> None:
    """Sibling files inside `.tripwire/` that aren't `events/` are still ignored."""
    locked = tmp_path / ".tripwire" / ".project.lock"
    assert _should_ignore(locked, tmp_path) is True


def test_classify_process_event_round_trip(tmp_path: Path) -> None:
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "v0710-routing"
    sid_dir.mkdir(parents=True)
    body = {
        "id": "evt-fire-1",
        "kind": "tripwire_fire",
        "session_id": "v0710-routing",
        "fired_at": "2026-04-26T14:32:18Z",
    }
    import json

    target = sid_dir / "0001.json"
    target.write_text(json.dumps(body), encoding="utf-8")

    ev = classify_process_event("proj-x", tmp_path, target)
    assert isinstance(ev, ProcessEvent)
    assert ev.project_id == "proj-x"
    assert ev.kind == "tripwire_fire"
    assert ev.session_id == "v0710-routing"
    assert ev.fired_at == "2026-04-26T14:32:18Z"
    assert ev.event_id == "firings/v0710-routing/1"


def test_classify_process_event_returns_none_for_non_event_path(
    tmp_path: Path,
) -> None:
    # An ordinary project file is not a process_event.
    other = tmp_path / "nodes" / "abc.yaml"
    assert classify_process_event("p", tmp_path, other) is None


def test_classify_process_event_returns_none_for_unreadable(
    tmp_path: Path,
) -> None:
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
    sid_dir.mkdir(parents=True)
    target = sid_dir / "0001.json"
    target.write_text("not valid json", encoding="utf-8")
    assert classify_process_event("p", tmp_path, target) is None


def test_classify_process_event_ignores_temp_files(tmp_path: Path) -> None:
    sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
    sid_dir.mkdir(parents=True)
    target = sid_dir / "0001.json.tmp"
    target.write_text("{}", encoding="utf-8")
    assert classify_process_event("p", tmp_path, target) is None
