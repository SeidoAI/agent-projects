"""Issue listing, detail, and mutation routes.

Endpoints implemented in KUI-27.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/issues", tags=["issues"]
)


@router.get("")
async def list_issues(project_id: str) -> list:
    """List issues for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
