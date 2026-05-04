"""Marker file machinery for heuristic suppression."""

from __future__ import annotations

import json
from pathlib import Path

from tripwire._internal.heuristics import (
    gc_markers,
    has_marker,
    marker_path,
    reset_markers,
    write_marker,
)
from tripwire._internal.heuristics._acks import (
    ACK_DIR_REL,
    PROJECT_SINGLETON_UUID,
    MarkerKey,
    condition_hash,
)


def test_condition_hash_deterministic():
    assert condition_hash("a", "b") == condition_hash("a", "b")
    assert condition_hash("a", "b") != condition_hash("a", "c")
    # Length is fixed at 12 chars.
    assert len(condition_hash("anything")) == 12


def test_marker_path_layout(tmp_path: Path):
    key = MarkerKey("v_stale_concept", "abc-123", "deadbeef0000")
    p = marker_path(tmp_path, key)
    expected = tmp_path / ACK_DIR_REL / "v_stale_concept" / "abc-123-deadbeef0000.json"
    assert p == expected


def test_write_marker_first_fire_pins_first_fired_at(tmp_path: Path):
    key = MarkerKey("v_mega_issue", "issue-uuid", "h1")
    write_marker(tmp_path, key, evidence_summary="first")

    p = marker_path(tmp_path, key)
    assert p.is_file()
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["first_fired_at"]
    assert payload["last_seen_at"] == payload["first_fired_at"]
    assert payload["evidence_summary"] == "first"


def test_write_marker_refresh_keeps_first_bumps_last(tmp_path: Path):
    key = MarkerKey("v_mega_issue", "issue-uuid", "h1")
    write_marker(tmp_path, key, evidence_summary="first")
    p = marker_path(tmp_path, key)
    initial = json.loads(p.read_text(encoding="utf-8"))

    # Sleep-free: the second write happens at a different microsecond
    # almost always; if it happens to land in the same instant, the
    # invariant ``first_fired_at <= last_seen_at`` still holds.
    write_marker(tmp_path, key, evidence_summary="refreshed")
    refreshed = json.loads(p.read_text(encoding="utf-8"))

    assert refreshed["first_fired_at"] == initial["first_fired_at"]
    assert refreshed["last_seen_at"] >= initial["last_seen_at"]
    assert refreshed["evidence_summary"] == "refreshed"


def test_has_marker_reflects_disk_state(tmp_path: Path):
    key = MarkerKey("v_node_ratio", PROJECT_SINGLETON_UUID, "h1")
    assert has_marker(tmp_path, key) is False
    write_marker(tmp_path, key)
    assert has_marker(tmp_path, key) is True


def test_condition_hash_change_re_fires(tmp_path: Path):
    """Different evidence → different hash → different marker filename.

    A new condition_hash is the entire mechanism for re-firing — the
    suppressed marker still sits on disk for the old hash, but the new
    hash has no marker, so ``has_marker`` returns False on the new key.
    """
    old_key = MarkerKey("v_stale_concept", "node-uuid", condition_hash("evidence-v1"))
    new_key = MarkerKey("v_stale_concept", "node-uuid", condition_hash("evidence-v2"))
    write_marker(tmp_path, old_key)

    assert has_marker(tmp_path, old_key) is True
    assert has_marker(tmp_path, new_key) is False


def test_reset_markers_by_id(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u2", "h2"))
    write_marker(tmp_path, MarkerKey("v_stale_concept", "u3", "h3"))

    removed = reset_markers(tmp_path, heuristic_id="v_mega_issue")
    assert removed == 2

    assert has_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1")) is False
    assert has_marker(tmp_path, MarkerKey("v_stale_concept", "u3", "h3")) is True


def test_reset_markers_by_id_and_entity(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u2", "h2"))

    removed = reset_markers(tmp_path, heuristic_id="v_mega_issue", entity_uuid="u1")
    assert removed == 1
    assert has_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1")) is False
    assert has_marker(tmp_path, MarkerKey("v_mega_issue", "u2", "h2")) is True


def test_reset_markers_all_clears_everything(tmp_path: Path):
    write_marker(tmp_path, MarkerKey("v_mega_issue", "u1", "h1"))
    write_marker(tmp_path, MarkerKey("v_stale_concept", "u3", "h3"))

    removed = reset_markers(tmp_path)
    assert removed == 2
    assert not (tmp_path / ACK_DIR_REL / "v_mega_issue").exists()
    assert not (tmp_path / ACK_DIR_REL / "v_stale_concept").exists()


def test_gc_markers_removes_only_dead_entities(tmp_path: Path):
    live_uuid = "live-entity"
    dead_uuid = "dead-entity"
    write_marker(tmp_path, MarkerKey("v_mega_issue", live_uuid, "h1"))
    write_marker(tmp_path, MarkerKey("v_mega_issue", dead_uuid, "h2"))
    write_marker(tmp_path, MarkerKey("v_node_ratio", PROJECT_SINGLETON_UUID, "h3"))

    removed = gc_markers(tmp_path, {live_uuid})
    assert removed == 1
    assert has_marker(tmp_path, MarkerKey("v_mega_issue", live_uuid, "h1")) is True
    assert has_marker(tmp_path, MarkerKey("v_mega_issue", dead_uuid, "h2")) is False
    # Project-singleton marker is always preserved.
    assert (
        has_marker(
            tmp_path, MarkerKey("v_node_ratio", PROJECT_SINGLETON_UUID, "h3")
        )
        is True
    )


def test_gc_with_no_marker_dir_is_noop(tmp_path: Path):
    assert gc_markers(tmp_path, set()) == 0


def test_reset_with_no_marker_dir_is_noop(tmp_path: Path):
    assert reset_markers(tmp_path) == 0
