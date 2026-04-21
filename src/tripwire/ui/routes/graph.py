"""Concept-graph and dependency-graph traversal routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/graph", tags=["graph"])

# Replace these 501 stubs when implementing the real endpoints.
# Next agent (KUI-29/30): wire via
#   from tripwire.ui.services.graph_service import (
#       build_concept_graph, build_dependency_graph, current_cache_version,
#   )
# `current_cache_version` is useful for ETag / response-cache headers.


@router.get("/deps")
async def get_dependency_graph(project_id: str) -> None:
    """Return the dependency graph for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/concept")
async def get_concept_graph(project_id: str) -> None:
    """Return the concept graph for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
