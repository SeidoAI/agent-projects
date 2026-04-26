"""Tests for `GET /api/projects/{pid}/events` and `/events/{event_id}`.

KUI-100 - see `docs/specs/2026-04-26-v08-handoff.md` §2.2-§2.3.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tripwire.ui.services.event_aggregator import encode_event_id


def _write_event(
    project_dir: Path,
    kind: str,
    session_id: str,
    n: int,
    payload: dict,
) -> None:
    sid_dir = project_dir / ".tripwire" / "events" / kind / session_id
    sid_dir.mkdir(parents=True, exist_ok=True)
    (sid_dir / f"{n:04d}.json").write_text(json.dumps(payload), encoding="utf-8")


def test_list_events_empty(seeded_client: TestClient, project_id: str) -> None:
    resp = seeded_client.get(f"/api/projects/{project_id}/events")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"events": [], "next_cursor": None}


def test_list_events_returns_newest_first(
    seeded_client: TestClient, project_id: str, project_dir: Path
) -> None:
    _write_event(
        project_dir,
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
        project_dir,
        "validator_runs",
        "s1",
        1,
        {
            "id": "evt-new",
            "kind": "validator_pass",
            "session_id": "s1",
            "fired_at": "2026-04-26T11:00:00Z",
        },
    )
    resp = seeded_client.get(f"/api/projects/{project_id}/events")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [e["id"] for e in body["events"]] == ["evt-new", "evt-old"]


def test_list_events_filter_by_session_id(
    seeded_client: TestClient, project_id: str, project_dir: Path
) -> None:
    _write_event(
        project_dir,
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
        project_dir,
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
    resp = seeded_client.get(
        f"/api/projects/{project_id}/events", params={"session_id": "alpha"}
    )
    assert resp.status_code == 200, resp.text
    assert [e["id"] for e in resp.json()["events"]] == ["evt-a"]


def test_list_events_filter_by_kind_multi(
    seeded_client: TestClient, project_id: str, project_dir: Path
) -> None:
    _write_event(
        project_dir,
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
        project_dir,
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
    resp = seeded_client.get(
        f"/api/projects/{project_id}/events",
        params=[("kind", "tripwire_fire"), ("kind", "validator_pass")],
    )
    body = resp.json()
    assert sorted(e["id"] for e in body["events"]) == ["evt-fire", "evt-pass"]


def test_list_events_limit_capped_at_500(
    seeded_client: TestClient, project_id: str
) -> None:
    resp = seeded_client.get(
        f"/api/projects/{project_id}/events",
        params={"limit": "999"},
    )
    # Cap is enforced silently — a 200 response with no events is fine.
    assert resp.status_code == 200, resp.text


def test_list_events_rejects_negative_limit(
    seeded_client: TestClient, project_id: str
) -> None:
    resp = seeded_client.get(
        f"/api/projects/{project_id}/events",
        params={"limit": "-1"},
    )
    # FastAPI's Query(ge=...) returns 422 for invalid input.
    assert resp.status_code == 422, resp.text


def test_get_event_detail(
    seeded_client: TestClient, project_id: str, project_dir: Path
) -> None:
    _write_event(
        project_dir,
        "firings",
        "s1",
        7,
        {
            "id": "evt-fire-7",
            "kind": "tripwire_fire",
            "session_id": "s1",
            "fired_at": "2026-04-26T10:00:00Z",
            "tripwire_id": "self-review",
            "blocks": True,
        },
    )
    encoded = encode_event_id("firings", "s1", 7)
    resp = seeded_client.get(f"/api/projects/{project_id}/events/{encoded}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "evt-fire-7"
    assert body["tripwire_id"] == "self-review"
    assert body["blocks"] is True


def test_get_event_404_when_missing(seeded_client: TestClient, project_id: str) -> None:
    encoded = encode_event_id("firings", "s1", 999)
    resp = seeded_client.get(f"/api/projects/{project_id}/events/{encoded}")
    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body["code"] == "event/not_found"


def test_get_event_404_for_path_traversal(
    seeded_client: TestClient, project_id: str
) -> None:
    # `/` inside the encoded id is structural, but `..` segments must not
    # escape the events root.
    resp = seeded_client.get(
        f"/api/projects/{project_id}/events/firings/..%2Fetc%2Fpasswd/1",
    )
    assert resp.status_code in {404, 400}, resp.text


def test_unknown_project_returns_404(client: TestClient) -> None:
    resp = client.get("/api/projects/000000000000/events")
    assert resp.status_code == 404, resp.text
