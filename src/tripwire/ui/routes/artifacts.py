"""Artifact manifest and per-session artifact routes.

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/projects/{project_id}", tags=["artifacts"])

# Replace these 501 stubs when implementing the real endpoints.


@router.get("/artifact-manifest")
async def get_artifact_manifest(project_id: str) -> None:
    """Return the artifact manifest for a project."""
    raise HTTPException(status_code=501, detail="Not yet implemented")


@router.get("/sessions/{session_id}/artifacts")
async def list_session_artifacts(project_id: str, session_id: str) -> None:
    """List artifacts for a session."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
