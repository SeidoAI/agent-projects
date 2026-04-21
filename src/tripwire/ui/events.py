"""Typed WebSocket event schema — v1 active + v2 stubs.

The backend emits these events via ``WebSocketHub.broadcast``; the frontend
mirrors the shapes in TypeScript (see ``[[websocket-event-contract]]``) and
dispatches to TanStack Query cache invalidations.

Every class inherits from :class:`Event` and declares a ``Literal[...]`` on
``type`` — that field is the pydantic discriminator used by
:data:`TripwireUiEvent` and :func:`parse_event` to route an incoming
payload to the correct subclass.

v1 active types emitted today: ``file_changed``, ``artifact_updated``,
``validation_completed``, ``ping``, ``pong``.

v2 stub types declared-but-never-emitted: ``container_status``,
``message_received``, ``github_event``, ``status_update``,
``pm_review_completed``, ``approval_pending``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


def _now() -> str:
    """Return a UTC ISO-8601 timestamp with millisecond precision."""
    return (
        datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class Event(BaseModel):
    """Base class for every WebSocket event.

    Subclasses override ``type`` with a ``Literal[...]`` to participate in
    the :data:`TripwireUiEvent` discriminated union.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    timestamp: str = Field(default_factory=_now)

    def to_json(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict for wire transmission."""
        return self.model_dump(mode="json")


# ---------------------------------------------------------------------------
# v1 — active event types
# ---------------------------------------------------------------------------


EntityType = Literal[
    "issue",
    "node",
    "session",
    "agent_def",
    "project",
    "enum",
    "artifact",
    "scoping-artifact",
]
FileAction = Literal["created", "modified", "deleted"]


class FileChangedEvent(Event):
    """A project-file write/delete classified by :func:`classify`."""

    type: Literal["file_changed"] = "file_changed"
    project_id: str
    entity_type: EntityType
    entity_id: str
    action: FileAction
    path: str


class ArtifactUpdatedEvent(Event):
    """A session artifact Markdown file changed on disk."""

    type: Literal["artifact_updated"] = "artifact_updated"
    project_id: str
    session_id: str
    artifact_name: str
    file: str


class ValidationCompletedEvent(Event):
    """A ``tripwire validate`` run finished; emitted by the action service."""

    type: Literal["validation_completed"] = "validation_completed"
    project_id: str
    errors: int
    warnings: int
    duration_ms: int


class PingEvent(Event):
    """Server → client heartbeat."""

    type: Literal["ping"] = "ping"


class PongEvent(Event):
    """Client → server heartbeat ack."""

    type: Literal["pong"] = "pong"


# ---------------------------------------------------------------------------
# v2 — declared-but-never-emitted stubs
# ---------------------------------------------------------------------------


ContainerStatus = Literal["running", "exited", "stopped"]


class ContainerStatusEvent(Event):
    type: Literal["container_status"] = "container_status"
    project_id: str
    session_id: str
    container_id: str
    status: ContainerStatus
    exit_code: int | None
    cpu_percent: str
    memory_usage: str


MessageDirection = Literal["agent_to_human", "human_to_agent"]


class MessageReceivedEvent(Event):
    type: Literal["message_received"] = "message_received"
    project_id: str
    session_id: str
    message_id: str
    direction: MessageDirection
    msg_type: str
    priority: str
    author: str
    preview: str


GitHubEventType = Literal[
    "checks_completed", "review_submitted", "pr_merged", "pr_closed"
]


class GitHubEvent(Event):
    type: Literal["github_event"] = "github_event"
    project_id: str
    event_type: GitHubEventType
    repo: str
    pr_number: int
    details: dict[str, Any]


class StatusUpdateEvent(Event):
    type: Literal["status_update"] = "status_update"
    project_id: str
    session_id: str
    state: str
    summary: str


class PmReviewCompletedEvent(Event):
    type: Literal["pm_review_completed"] = "pm_review_completed"
    project_id: str
    repo: str
    pr_number: int
    passed: bool
    failed_checks: list[str]


class ApprovalPendingEvent(Event):
    type: Literal["approval_pending"] = "approval_pending"
    project_id: str
    session_id: str
    artifact_name: str
    agent: str


# ---------------------------------------------------------------------------
# Discriminated union + parse helper
# ---------------------------------------------------------------------------


TripwireUiEvent = Annotated[
    (
        # v1
        FileChangedEvent
        | ArtifactUpdatedEvent
        | ValidationCompletedEvent
        | PingEvent
        | PongEvent
        # v2 stubs
        | ContainerStatusEvent
        | MessageReceivedEvent
        | GitHubEvent
        | StatusUpdateEvent
        | PmReviewCompletedEvent
        | ApprovalPendingEvent
    ),
    Field(discriminator="type"),
]


_event_adapter: TypeAdapter[TripwireUiEvent] = TypeAdapter(TripwireUiEvent)


def parse_event(payload: dict[str, Any]) -> Event:
    """Validate *payload* and return the matching :class:`Event` subclass.

    Dispatch is driven by the ``type`` field; an unknown or missing value
    raises ``pydantic.ValidationError``.
    """
    return _event_adapter.validate_python(payload)


__all__ = [
    "ApprovalPendingEvent",
    "ArtifactUpdatedEvent",
    "ContainerStatusEvent",
    "Event",
    "FileChangedEvent",
    "GitHubEvent",
    "MessageReceivedEvent",
    "PingEvent",
    "PmReviewCompletedEvent",
    "PongEvent",
    "StatusUpdateEvent",
    "TripwireUiEvent",
    "ValidationCompletedEvent",
    "parse_event",
]
