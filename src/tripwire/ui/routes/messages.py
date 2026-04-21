"""Message routes (v2 stub — 501 Not Implemented)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/messages", tags=["messages (v2)"])

_V2 = HTTPException(status_code=501, detail="Not implemented in v1")


@router.post("")
async def create_message() -> None:
    raise _V2


@router.get("")
async def list_messages() -> None:
    raise _V2


@router.get("/unread")
async def list_unread() -> None:
    raise _V2
