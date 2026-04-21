"""Issue listing, detail, and mutation routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}/issues", tags=["issues"])

# Replace these 501 stubs when implementing the real endpoints.
# Next agent (KUI-27): wire via
#   from tripwire.ui.services.issue_service import (
#       IssueFilters, get_issue, list_issues, validate_issue,
#   )
# `get_issue` raises FileNotFoundError on miss — translate to 404.


@router.get("")
async def list_issues(project_id: str) -> None:
    """List issues for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
