"""Tests for the `process_event` typed event class.

KUI-100 — see `docs/specs/2026-04-26-v08-handoff.md` §2.4.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tripwire.ui.events import ProcessEvent, parse_event


def test_process_event_round_trips() -> None:
    ev = ProcessEvent(
        project_id="proj-x",
        event_id="evt-001",
        kind="tripwire_fire",
        session_id="v0710-routing",
        fired_at="2026-04-26T14:32:18Z",
    )
    payload = ev.to_json()
    assert payload["type"] == "process_event"
    assert payload["project_id"] == "proj-x"
    assert payload["event_id"] == "evt-001"
    assert payload["kind"] == "tripwire_fire"
    assert payload["session_id"] == "v0710-routing"
    assert payload["fired_at"] == "2026-04-26T14:32:18Z"


def test_parse_event_dispatches_to_process_event() -> None:
    payload = {
        "type": "process_event",
        "project_id": "proj-x",
        "event_id": "evt-002",
        "kind": "validator_fail",
        "session_id": "recon",
        "fired_at": "2026-04-26T13:18:02Z",
    }
    ev = parse_event(payload)
    assert isinstance(ev, ProcessEvent)
    assert ev.kind == "validator_fail"


def test_process_event_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        ProcessEvent(
            project_id="p",
            event_id="evt",
            kind="status_transition",
            session_id="s",
            fired_at="2026-04-26T00:00:00Z",
            extra="nope",  # type: ignore[call-arg]
        )


def test_process_event_requires_session_id() -> None:
    with pytest.raises(ValidationError):
        ProcessEvent(
            project_id="p",
            event_id="evt",
            kind="status_transition",
            fired_at="2026-04-26T00:00:00Z",
        )  # type: ignore[call-arg]
