"""Issue listing, detail, and mutation routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/issues", tags=["issues"]
)

# Replace these 501 stubs when implementing the real endpoints.


@router.get("")
async def list_issues(project_id: str) -> None:
    """List issues for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
