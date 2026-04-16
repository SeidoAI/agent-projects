"""Concept-node listing and detail routes.

Endpoints implemented in KUI-28.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/nodes", tags=["nodes"]
)


@router.get("")
async def list_nodes(project_id: str) -> list:
    """List concept nodes for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
