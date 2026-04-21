"""Tests for tripwire.ui.events — discriminated union + round-trip."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from tripwire.ui.events import (
    ApprovalPendingEvent,
    ArtifactUpdatedEvent,
    ContainerStatusEvent,
    Event,
    FileChangedEvent,
    GitHubEvent,
    MessageReceivedEvent,
    PingEvent,
    PmReviewCompletedEvent,
    PongEvent,
    StatusUpdateEvent,
    TripwireUiEvent,  # noqa: F401 — imported to assert it is exported
    ValidationCompletedEvent,
    parse_event,
)

# ---------------------------------------------------------------------------
# v1 construction + serialisation
# ---------------------------------------------------------------------------


class TestFileChangedEvent:
    def test_builds_with_required_fields(self):
        ev = FileChangedEvent(
            project_id="abc123abc123",
            entity_type="issue",
            entity_id="KUI-42",
            action="modified",
            path="issues/KUI-42/issue.yaml",
        )
        assert ev.type == "file_changed"

    def test_timestamp_is_iso_utc(self):
        ev = FileChangedEvent(
            project_id="p",
            entity_type="node",
            entity_id="n",
            action="created",
            path="nodes/n.yaml",
        )
        # 2026-04-21T12:34:56.789Z
        assert re.match(
            r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$", ev.timestamp
        )

    def test_to_json_has_all_fields(self):
        ev = FileChangedEvent(
            project_id="p",
            entity_type="session",
            entity_id="s",
            action="deleted",
            path="sessions/s/session.yaml",
        )
        d = ev.to_json()
        assert d["type"] == "file_changed"
        assert set(d) == {
            "type",
            "timestamp",
            "project_id",
            "entity_type",
            "entity_id",
            "action",
            "path",
        }

    def test_unknown_entity_type_rejected(self):
        with pytest.raises(ValidationError):
            FileChangedEvent(
                project_id="p",
                entity_type="bogus",  # type: ignore[arg-type]
                entity_id="x",
                action="modified",
                path="x",
            )

    def test_unknown_action_rejected(self):
        with pytest.raises(ValidationError):
            FileChangedEvent(
                project_id="p",
                entity_type="issue",
                entity_id="x",
                action="renamed",  # type: ignore[arg-type]
                path="x",
            )

    def test_extra_field_rejected(self):
        with pytest.raises(ValidationError):
            FileChangedEvent(
                project_id="p",
                entity_type="issue",
                entity_id="x",
                action="modified",
                path="x",
                extra="nope",  # type: ignore[call-arg]
            )


class TestArtifactUpdatedEvent:
    def test_fields(self):
        ev = ArtifactUpdatedEvent(
            project_id="p",
            session_id="backend-realtime",
            artifact_name="task-checklist",
            file="task-checklist.md",
        )
        assert ev.type == "artifact_updated"
        assert ev.to_json()["artifact_name"] == "task-checklist"


class TestValidationCompletedEvent:
    def test_counts_are_ints(self):
        ev = ValidationCompletedEvent(
            project_id="p", errors=0, warnings=3, duration_ms=142
        )
        d = ev.to_json()
        assert d == {
            "type": "validation_completed",
            "timestamp": ev.timestamp,
            "project_id": "p",
            "errors": 0,
            "warnings": 3,
            "duration_ms": 142,
        }


class TestPingPong:
    def test_ping_type_default(self):
        assert PingEvent().type == "ping"

    def test_pong_type_default(self):
        assert PongEvent().type == "pong"


# ---------------------------------------------------------------------------
# v2 — declared-but-never-emitted
# ---------------------------------------------------------------------------


class TestV2Stubs:
    def test_container_status_required(self):
        ev = ContainerStatusEvent(
            session_id="s",
            container_id="c",
            status="running",
            exit_code=None,
            cpu_percent="12.5",
            memory_usage="128MiB",
        )
        assert ev.type == "container_status"
        assert ev.exit_code is None

    def test_container_status_exit_code_required_key(self):
        # exit_code is required (may be None, but must be present).
        with pytest.raises(ValidationError):
            ContainerStatusEvent(  # type: ignore[call-arg]
                session_id="s",
                container_id="c",
                status="exited",
                cpu_percent="0",
                memory_usage="0",
            )

    def test_message_received(self):
        ev = MessageReceivedEvent(
            session_id="s",
            message_id="m",
            direction="agent_to_human",
            msg_type="plan_approval",
            priority="blocking",
            author="pm",
            preview="…",
        )
        assert ev.type == "message_received"

    def test_github_event(self):
        ev = GitHubEvent(
            event_type="checks_completed",
            repo="SeidoAI/tripwire",
            pr_number=42,
            details={"conclusion": "success"},
        )
        assert ev.type == "github_event"
        assert ev.details["conclusion"] == "success"

    def test_status_update(self):
        ev = StatusUpdateEvent(
            session_id="s", state="implementing", summary="writing tests"
        )
        assert ev.type == "status_update"

    def test_pm_review_completed(self):
        ev = PmReviewCompletedEvent(
            repo="SeidoAI/tripwire",
            pr_number=7,
            passed=False,
            failed_checks=["verification_checklist"],
        )
        assert ev.type == "pm_review_completed"

    def test_approval_pending(self):
        ev = ApprovalPendingEvent(
            session_id="s", artifact_name="plan", agent="pm"
        )
        assert ev.type == "approval_pending"


# ---------------------------------------------------------------------------
# Discriminator dispatch + parse_event helper
# ---------------------------------------------------------------------------


class TestParseEvent:
    def test_dispatches_to_file_changed(self):
        ev = parse_event(
            {
                "type": "file_changed",
                "timestamp": "2026-04-21T10:00:00.000Z",
                "project_id": "p",
                "entity_type": "issue",
                "entity_id": "KUI-1",
                "action": "modified",
                "path": "issues/KUI-1/issue.yaml",
            }
        )
        assert isinstance(ev, FileChangedEvent)
        assert ev.entity_id == "KUI-1"

    def test_dispatches_to_ping(self):
        ev = parse_event({"type": "ping", "timestamp": "2026-04-21T00:00:00.000Z"})
        assert isinstance(ev, PingEvent)

    def test_dispatches_to_pong(self):
        ev = parse_event({"type": "pong", "timestamp": "2026-04-21T00:00:00.000Z"})
        assert isinstance(ev, PongEvent)

    def test_unknown_type_raises(self):
        with pytest.raises(ValidationError):
            parse_event({"type": "not_a_real_event"})

    def test_missing_type_raises(self):
        with pytest.raises(ValidationError):
            parse_event({})


class TestRoundTrip:
    @pytest.mark.parametrize(
        "event",
        [
            FileChangedEvent(
                project_id="p",
                entity_type="issue",
                entity_id="KUI-1",
                action="modified",
                path="issues/KUI-1/issue.yaml",
            ),
            ArtifactUpdatedEvent(
                project_id="p",
                session_id="s",
                artifact_name="plan",
                file="plan.md",
            ),
            ValidationCompletedEvent(
                project_id="p", errors=1, warnings=2, duration_ms=10
            ),
            PingEvent(),
            PongEvent(),
            ContainerStatusEvent(
                session_id="s",
                container_id="c",
                status="running",
                exit_code=None,
                cpu_percent="1",
                memory_usage="1",
            ),
            MessageReceivedEvent(
                session_id="s",
                message_id="m",
                direction="agent_to_human",
                msg_type="plan_approval",
                priority="blocking",
                author="pm",
                preview="…",
            ),
            GitHubEvent(
                event_type="pr_merged",
                repo="r",
                pr_number=1,
                details={},
            ),
            StatusUpdateEvent(
                session_id="s", state="implementing", summary="x"
            ),
            PmReviewCompletedEvent(
                repo="r", pr_number=1, passed=True, failed_checks=[]
            ),
            ApprovalPendingEvent(
                session_id="s", artifact_name="plan", agent="pm"
            ),
        ],
    )
    def test_to_json_parse_to_json(self, event: Event):
        payload = event.to_json()
        round_tripped = parse_event(payload)
        assert round_tripped.to_json() == payload
        assert type(round_tripped) is type(event)
