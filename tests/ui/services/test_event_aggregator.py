"""Tests for `tripwire.ui.services.event_aggregator`.

KUI-100 — see `docs/specs/2026-04-26-v08-handoff.md` §2.2 for the on-disk
layout (`.tripwire/events/<kind>/<sid>/<n>.json`) the aggregator reads.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tripwire.ui.services.event_aggregator import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    EventNotFoundError,
    encode_event_id,
    get_event,
    list_events,
)


def _write_event(
    project_dir: Path,
    kind: str,
    session_id: str,
    n: int,
    payload: dict,
) -> Path:
    """Write `<project>/.tripwire/events/<kind>/<sid>/<n:04d>.json` and return it."""
    sid_dir = project_dir / ".tripwire" / "events" / kind / session_id
    sid_dir.mkdir(parents=True, exist_ok=True)
    path = sid_dir / f"{n:04d}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


class TestListEvents:
    def test_empty_project_returns_empty_page(self, tmp_path: Path) -> None:
        page = list_events(tmp_path)
        assert page.events == []
        assert page.next_cursor is None

    def test_returns_events_newest_first(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "s1",
            1,
            {
                "id": "evt-a",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "firings",
            "s1",
            2,
            {
                "id": "evt-b",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T11:00:00Z",
            },
        )
        page = list_events(tmp_path)
        assert [e["id"] for e in page.events] == ["evt-b", "evt-a"]

    def test_aggregates_across_kind_subdirs(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "s1",
            1,
            {
                "id": "evt-fire",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "validator_runs",
            "s1",
            1,
            {
                "id": "evt-pass",
                "kind": "validator_pass",
                "session_id": "s1",
                "fired_at": "2026-04-26T11:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "rejections",
            "s1",
            1,
            {
                "id": "evt-rej",
                "kind": "artifact_rejected",
                "session_id": "s1",
                "fired_at": "2026-04-26T12:00:00Z",
            },
        )
        page = list_events(tmp_path)
        assert [e["id"] for e in page.events] == ["evt-rej", "evt-pass", "evt-fire"]

    def test_filter_by_session_id(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "alpha",
            1,
            {
                "id": "evt-a",
                "kind": "tripwire_fire",
                "session_id": "alpha",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "firings",
            "beta",
            1,
            {
                "id": "evt-b",
                "kind": "tripwire_fire",
                "session_id": "beta",
                "fired_at": "2026-04-26T11:00:00Z",
            },
        )
        page = list_events(tmp_path, session_id="alpha")
        assert [e["id"] for e in page.events] == ["evt-a"]

    def test_filter_by_kind_multi(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "s1",
            1,
            {
                "id": "evt-fire",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "validator_runs",
            "s1",
            1,
            {
                "id": "evt-pass",
                "kind": "validator_pass",
                "session_id": "s1",
                "fired_at": "2026-04-26T11:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "rejections",
            "s1",
            1,
            {
                "id": "evt-rej",
                "kind": "artifact_rejected",
                "session_id": "s1",
                "fired_at": "2026-04-26T12:00:00Z",
            },
        )
        page = list_events(tmp_path, kinds=["tripwire_fire", "artifact_rejected"])
        assert sorted(e["id"] for e in page.events) == ["evt-fire", "evt-rej"]

    def test_filter_by_since(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "s1",
            1,
            {
                "id": "evt-old",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        _write_event(
            tmp_path,
            "firings",
            "s1",
            2,
            {
                "id": "evt-new",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T13:00:00Z",
            },
        )
        page = list_events(tmp_path, since="2026-04-26T12:00:00Z")
        assert [e["id"] for e in page.events] == ["evt-new"]

    def test_default_limit_used(self, tmp_path: Path) -> None:
        for i in range(DEFAULT_LIMIT + 5):
            _write_event(
                tmp_path,
                "firings",
                "s1",
                i + 1,
                {
                    "id": f"evt-{i:03d}",
                    "kind": "tripwire_fire",
                    "session_id": "s1",
                    "fired_at": f"2026-04-26T{i:02d}:00:00Z",
                },
            )
        page = list_events(tmp_path)
        assert len(page.events) == DEFAULT_LIMIT
        assert page.next_cursor is not None

    def test_limit_capped_at_max(self, tmp_path: Path) -> None:
        for i in range(3):
            _write_event(
                tmp_path,
                "firings",
                "s1",
                i + 1,
                {
                    "id": f"evt-{i}",
                    "kind": "tripwire_fire",
                    "session_id": "s1",
                    "fired_at": f"2026-04-26T0{i}:00:00Z",
                },
            )
        # An over-cap limit gets clamped to MAX_LIMIT — still returns all 3.
        page = list_events(tmp_path, limit=MAX_LIMIT + 100)
        assert len(page.events) == 3

    def test_cursor_paginates(self, tmp_path: Path) -> None:
        for i in range(5):
            _write_event(
                tmp_path,
                "firings",
                "s1",
                i + 1,
                {
                    "id": f"evt-{i}",
                    "kind": "tripwire_fire",
                    "session_id": "s1",
                    "fired_at": f"2026-04-26T0{i}:00:00Z",
                },
            )
        page1 = list_events(tmp_path, limit=2)
        # Newest-first: evt-4, evt-3.
        assert [e["id"] for e in page1.events] == ["evt-4", "evt-3"]
        assert page1.next_cursor is not None
        page2 = list_events(tmp_path, limit=2, cursor=page1.next_cursor)
        assert [e["id"] for e in page2.events] == ["evt-2", "evt-1"]
        page3 = list_events(tmp_path, limit=2, cursor=page2.next_cursor)
        assert [e["id"] for e in page3.events] == ["evt-0"]
        assert page3.next_cursor is None

    def test_skips_corrupt_files(self, tmp_path: Path) -> None:
        sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
        sid_dir.mkdir(parents=True)
        (sid_dir / "0001.json").write_text("not valid json", encoding="utf-8")
        _write_event(
            tmp_path,
            "firings",
            "s1",
            2,
            {
                "id": "evt-ok",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        page = list_events(tmp_path)
        assert [e["id"] for e in page.events] == ["evt-ok"]

    def test_ignores_temp_files(self, tmp_path: Path) -> None:
        sid_dir = tmp_path / ".tripwire" / "events" / "firings" / "s1"
        sid_dir.mkdir(parents=True)
        (sid_dir / "0001.json.tmp").write_text("{}", encoding="utf-8")
        _write_event(
            tmp_path,
            "firings",
            "s1",
            1,
            {
                "id": "evt-ok",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        page = list_events(tmp_path)
        assert [e["id"] for e in page.events] == ["evt-ok"]


# ---------------------------------------------------------------------------
# get_event / encode_event_id
# ---------------------------------------------------------------------------


class TestGetEvent:
    def test_get_event_round_trip_with_encoded_id(self, tmp_path: Path) -> None:
        _write_event(
            tmp_path,
            "firings",
            "s1",
            7,
            {
                "id": "evt-fire-7",
                "kind": "tripwire_fire",
                "session_id": "s1",
                "fired_at": "2026-04-26T10:00:00Z",
            },
        )
        encoded = encode_event_id("firings", "s1", 7)
        body = get_event(tmp_path, encoded)
        assert body["id"] == "evt-fire-7"
        assert body["kind"] == "tripwire_fire"

    def test_get_event_missing_raises(self, tmp_path: Path) -> None:
        encoded = encode_event_id("firings", "s1", 1)
        with pytest.raises(EventNotFoundError):
            get_event(tmp_path, encoded)

    def test_get_event_rejects_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(EventNotFoundError):
            get_event(tmp_path, "firings/../etc/passwd/0001")

    def test_get_event_rejects_garbage_id(self, tmp_path: Path) -> None:
        with pytest.raises(EventNotFoundError):
            get_event(tmp_path, "not-a-valid-id")
