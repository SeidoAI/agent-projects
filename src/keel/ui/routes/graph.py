"""Concept-graph and dependency-graph traversal routes.

Endpoints implemented in KUI-29.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/graph", tags=["graph"]
)


@router.get("/deps")
async def get_dependency_graph(project_id: str) -> dict:
    """Return the dependency graph for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/concept")
async def get_concept_graph(project_id: str) -> dict:
    """Return the concept graph for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
