"""PM review routes (v2 stub — 501 Not Implemented)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/pm-reviews",
    tags=["pm-reviews (v2)"],
)

_V2 = HTTPException(status_code=501, detail="Not implemented in v1")


@router.get("")
async def list_pm_reviews(project_id: str) -> None:
    raise _V2
