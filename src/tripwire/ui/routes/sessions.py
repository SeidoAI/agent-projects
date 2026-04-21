"""Session listing and detail routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/sessions", tags=["sessions"])

# Replace these 501 stubs when implementing the real endpoints.


@router.get("")
async def list_sessions(project_id: str) -> None:
    """List sessions for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
