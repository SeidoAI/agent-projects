"""Enum descriptor routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/enums", tags=["enums"])

# Replace these 501 stubs when implementing the real endpoints.


@router.get("/{name}")
async def get_enum(project_id: str, name: str) -> None:
    """Return an enum descriptor."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
