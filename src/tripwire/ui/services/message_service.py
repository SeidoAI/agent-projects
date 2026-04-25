"""Agent-messaging service placeholder (v2 stub).

v1 has no containers, so the agent-inbox is always empty. v2 will add a
sqlite-backed message store; until then every method raises
``NotImplementedError`` and every route returns 501.

No ``sqlite3`` imports live here — the DB lifecycle is owned by v2.
See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

_NI_MESSAGE = (
    "tripwire.containers/agent-messaging is not yet implemented (v2). "
    "See docs/agent-containers.md."
)


# ---------------------------------------------------------------------------
# DTOs (OpenAPI-only; never returned in v1)
# ---------------------------------------------------------------------------


class Message(BaseModel):
    """Full agent message record."""

    id: str
    session_id: str
    type: str
    priority: str
    body: str
    decision: str | None = None
    created_at: datetime
    responded_at: datetime | None = None


class MessageCreate(BaseModel):
    """Request body for ``POST /api/messages``."""

    session_id: str
    type: str
    priority: str
    body: str


class MessageRespond(BaseModel):
    """Request body for ``POST /api/messages/{id}/respond``."""

    body: str
    decision: str | None = None


class UnreadCount(BaseModel):
    """Blocking-unread count response for the badge."""

    count: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MessageService:
    """Placeholder agent-messaging service.

    Every method raises :class:`NotImplementedError`; the v2 implementation
    lands alongside ``tripwire.containers``.
    """

    def create(
        self,
        session_id: str,
        type: str,
        priority: str,
        body: str,
    ) -> Message:
        raise NotImplementedError(_NI_MESSAGE)

    def list(self, session_id: str) -> list[Message]:
        raise NotImplementedError(_NI_MESSAGE)

    def get_pending(self, session_id: str) -> list[Message]:
        raise NotImplementedError(_NI_MESSAGE)

    def respond(
        self,
        message_id: str,
        body: str,
        decision: str | None = None,
    ) -> Message:
        raise NotImplementedError(_NI_MESSAGE)

    def unread_count(self) -> UnreadCount:
        raise NotImplementedError(_NI_MESSAGE)

    def finalize(self, session_id: str, project_dir: str) -> None:
        raise NotImplementedError(_NI_MESSAGE)
