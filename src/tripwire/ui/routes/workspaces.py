"""Workspace listing endpoint.

Surface for the v0.10.0 UI workspace switcher. The actual workspace
overview / dashboard page is deferred to v0.10.1 — this endpoint just
returns enough metadata for the dropdown to group projects by their
parent workspace.
"""

from __future__ import annotations

from fastapi import APIRouter

from tripwire.ui.services.workspace_service import (
    WorkspaceSummary,
    list_workspaces,
)

router = APIRouter(prefix="/api", tags=["workspaces"])


@router.get("/workspaces", response_model=list[WorkspaceSummary])
async def list_workspaces_route() -> list[WorkspaceSummary]:
    """Return every discovered workspace.

    Driven by ``config.workspace_roots`` in ``~/.tripwire/config.yaml``
    (set via ``tripwire config set workspace-roots ...``). An empty
    list means no workspaces are registered yet — the UI degrades to
    a flat (ungrouped) project list.
    """
    return list_workspaces()
