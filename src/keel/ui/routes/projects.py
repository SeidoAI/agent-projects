"""Project listing and detail routes.

Endpoints implemented in KUI-26.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects() -> list:
    """List discovered projects."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/{project_id}")
async def get_project(project_id: str) -> dict:
    """Get project detail."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
