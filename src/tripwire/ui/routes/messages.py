"""Message routes (v2 stub — 501 Not Implemented).

Every endpoint returns 501 via the shared ``raise_v2_not_implemented``
helper. DTOs are declared on :mod:`tripwire.ui.services.message_service`
so OpenAPI lists realistic shapes for frontend type generation.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from fastapi import APIRouter

from tripwire.ui.routes._v2_stub import V2_RESPONSES, raise_v2_not_implemented
from tripwire.ui.services.message_service import (
    Message,
    MessageCreate,
    MessageRespond,
    UnreadCount,
)

router = APIRouter(prefix="/api/messages", tags=["messages (v2)"])

_DETAIL = (
    "messages feature requires tripwire.containers agent-messaging "
    "(v2 — not yet implemented)"
)


@router.post("", response_model=Message, responses=V2_RESPONSES)
async def create_message(body: MessageCreate) -> Message:
    raise_v2_not_implemented(_DETAIL)


@router.get("", response_model=list[Message], responses=V2_RESPONSES)
async def list_messages(session_id: str) -> list[Message]:
    raise_v2_not_implemented(_DETAIL)


@router.get("/pending", response_model=list[Message], responses=V2_RESPONSES)
async def list_pending_messages(session_id: str) -> list[Message]:
    raise_v2_not_implemented(_DETAIL)


@router.post("/{message_id}/respond", response_model=Message, responses=V2_RESPONSES)
async def respond_to_message(message_id: str, body: MessageRespond) -> Message:
    raise_v2_not_implemented(_DETAIL)


@router.get("/unread", response_model=UnreadCount)
async def get_unread_count() -> UnreadCount:
    # v1 has no agent containers, so the inbox is always empty. v2 will
    # replace this with a sqlite-backed query (see [[dec-v2-stubs-not-deferred]]).
    return UnreadCount(count=0)
