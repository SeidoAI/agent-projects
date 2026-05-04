"""Workflow graph route (KUI-100).

Single endpoint:

    GET  /api/projects/{project_id}/workflow

Returns the workflow territory payload: `workflow.yaml` definitions,
shallow registry metadata, and workflow drift findings. PM-mode header
(`X-Tripwire-Role: pm`) controls whether JIT prompt `prompt_revealed`
fields are populated.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.services.role_gate import is_pm
from tripwire.ui.services.workflow_service import build_workflow

router = APIRouter(prefix="/api/projects/{project_id}", tags=["workflow"])


@router.get("/workflow")
async def get_workflow_route(
    request: Request,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> dict[str, Any]:
    """Return the workflow territory payload, with PM-mode redaction applied."""
    return build_workflow(
        project.project_dir,
        project_id=project.project_id,
        is_pm_role=is_pm(request),
    )
