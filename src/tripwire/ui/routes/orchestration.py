"""Orchestration-pattern routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(
    prefix="/api/projects/{project_id}/orchestration",
    tags=["orchestration"],
)

# Replace these 501 stubs when implementing the real endpoints.
# Next agent (KUI-33): wire via
#   from tripwire.ui.services.orchestration_service import (
#       get_active_pattern, get_session_pattern,
#   )
# Both raise FileNotFoundError on missing pattern yaml — translate to 404.


@router.get("/pattern")
async def get_orchestration_pattern(project_id: str) -> None:
    """Return the orchestration pattern for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
