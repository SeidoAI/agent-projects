"""Session listing and detail routes.

Endpoints implemented in KUI-30.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/sessions", tags=["sessions"]
)


@router.get("")
async def list_sessions(project_id: str) -> list:
    """List sessions for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
