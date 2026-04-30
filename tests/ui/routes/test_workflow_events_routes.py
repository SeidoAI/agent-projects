"""Workflow events log routes (KUI-155 / KUI-156).

Tests the new ``/api/projects/{pid}/workflow-events`` and
``/api/projects/{pid}/workflow-stats`` endpoints. These are distinct
from the existing ``/api/projects/{pid}/events`` (v0.8 emitter) — the
new endpoints read from the v0.9 events log substrate
(:mod:`tripwire.core.events.log`).
"""

from __future__ import annotations

from pathlib import Path


def _seed_workflow_events(pd: Path) -> None:
    from tripwire.core.events.log import emit_event

    emit_event(
        pd,
        workflow="coding-session",
        instance="sess-1",
        station="executing",
        event="validator.run",
        details={"id": "v_uuid_present", "outcome": "pass"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="sess-1",
        station="executing",
        event="validator.run",
        details={"id": "v_reference_integrity", "outcome": "fail"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="sess-1",
        station="in_review",
        event="transition.completed",
        details={"from_station": "executing", "to_station": "in_review"},
    )
    emit_event(
        pd,
        workflow="coding-session",
        instance="sess-2",
        station="executing",
        event="tripwire.fired",
        details={"id": "tw_self_review", "session_id": "sess-2"},
    )


def test_workflow_events_lists_chronologically(seeded_client, project_dir, project_id):
    _seed_workflow_events(project_dir)

    response = seeded_client.get(
        f"/api/projects/{project_id}/workflow-events"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "events" in body
    events = body["events"]
    assert len(events) == 4
    # Each row carries the v0.9 schema fields.
    for row in events:
        assert "ts" in row
        assert "workflow" in row
        assert "instance" in row
        assert "station" in row
        assert "event" in row
        assert "details" in row


def test_workflow_events_filters_by_instance(
    seeded_client, project_dir, project_id
):
    _seed_workflow_events(project_dir)

    response = seeded_client.get(
        f"/api/projects/{project_id}/workflow-events?instance=sess-1"
    )
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert len(events) == 3
    assert all(e["instance"] == "sess-1" for e in events)


def test_workflow_events_filters_by_event_kind(
    seeded_client, project_dir, project_id
):
    _seed_workflow_events(project_dir)

    response = seeded_client.get(
        f"/api/projects/{project_id}/workflow-events?event=validator.run"
    )
    assert response.status_code == 200, response.text
    events = response.json()["events"]
    assert len(events) == 2
    assert all(e["event"] == "validator.run" for e in events)


def test_workflow_events_empty_log(seeded_client, project_dir, project_id):
    """No events directory → empty list, no error."""
    response = seeded_client.get(f"/api/projects/{project_id}/workflow-events")
    assert response.status_code == 200, response.text
    assert response.json()["events"] == []


def test_workflow_stats_returns_aggregate_counts(
    seeded_client, project_dir, project_id
):
    """``workflow-stats`` aggregates counts by event kind + per-instance."""
    _seed_workflow_events(project_dir)

    response = seeded_client.get(
        f"/api/projects/{project_id}/workflow-stats"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 4
    by_kind = body["by_kind"]
    assert by_kind["validator.run"] == 2
    assert by_kind["transition.completed"] == 1
    assert by_kind["tripwire.fired"] == 1
    by_instance = body["by_instance"]
    assert by_instance["sess-1"] == 3
    assert by_instance["sess-2"] == 1


def test_workflow_stats_top_n_rules(
    seeded_client, project_dir, project_id
):
    """Stats surfaces a top-N rules table keyed on details.id."""
    from tripwire.core.events.log import emit_event

    # Many fires of one validator + a few of another.
    for _ in range(5):
        emit_event(
            project_dir,
            workflow="coding-session",
            instance="sess-3",
            station="executing",
            event="validator.run",
            details={"id": "v_freshness", "outcome": "fail"},
        )
    for _ in range(2):
        emit_event(
            project_dir,
            workflow="coding-session",
            instance="sess-3",
            station="executing",
            event="validator.run",
            details={"id": "v_uuid_present", "outcome": "fail"},
        )

    response = seeded_client.get(
        f"/api/projects/{project_id}/workflow-stats?top_n=2"
    )
    assert response.status_code == 200, response.text
    rules = response.json().get("top_rules") or []
    assert len(rules) <= 2
    ids = [r["id"] for r in rules]
    assert "v_freshness" in ids
