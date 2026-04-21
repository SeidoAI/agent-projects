"""Container management routes (v2 stub — 501 Not Implemented)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/containers", tags=["containers (v2)"])

_V2 = HTTPException(status_code=501, detail="Not implemented in v1")


@router.get("")
async def list_containers() -> None:
    raise _V2


@router.post("/launch")
async def launch_container() -> None:
    raise _V2
