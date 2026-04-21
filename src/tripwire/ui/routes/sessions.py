"""Session listing and detail routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/sessions", tags=["sessions"])

# Replace these 501 stubs when implementing the real endpoints.
# Next agent (KUI-31): wire via
#   from tripwire.ui.services.session_service import get_session, list_sessions
# `get_session` raises FileNotFoundError — translate to 404; ValueError
# from broken session.yaml — translate to 500.


@router.get("")
async def list_sessions(project_id: str) -> None:
    """List sessions for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
