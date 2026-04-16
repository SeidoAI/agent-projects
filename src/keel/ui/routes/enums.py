"""Enum descriptor routes.

Endpoints implemented in KUI-32.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/enums", tags=["enums"]
)


@router.get("/{name}")
async def get_enum(project_id: str, name: str) -> dict:
    """Return an enum descriptor."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
