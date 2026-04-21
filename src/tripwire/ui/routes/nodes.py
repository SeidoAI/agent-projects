"""Concept-node listing and detail routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/nodes", tags=["nodes"])

# Replace these 501 stubs when implementing the real endpoints.
# Next agent (KUI-28): wire via
#   from tripwire.ui.services.node_service import (
#       check_all_freshness, get_node, list_nodes, reverse_refs,
#   )
# `get_node` raises ValueError on bad slug, FileNotFoundError on miss —
# translate to 400 and 404 respectively.


@router.get("")
async def list_nodes(project_id: str) -> None:
    """List concept nodes for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
