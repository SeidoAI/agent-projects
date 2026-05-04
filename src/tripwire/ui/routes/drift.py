"""Drift report route — KUI-157 / I4.

Single endpoint:

    GET  /api/projects/{project_id}/drift

Returns the unified coherence score, per-signal breakdown, and active
workflow drift findings for the Drift Report UI screen. Wraps the
existing ``tripwire.core.drift.compute_coherence`` substrate.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from tripwire.core.drift import compute_coherence, drift_finding_to_dict
from tripwire.ui.dependencies import ProjectContext, get_project

router = APIRouter(prefix="/api/projects/{project_id}", tags=["drift"])


@router.get("/drift")
async def get_drift_route(
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> dict[str, Any]:
    """Return ``{score, breakdown, workflow_drift_findings}``."""
    report = compute_coherence(project.project_dir)
    return {
        "score": report.score,
        "breakdown": report.breakdown,
        "workflow_drift_findings": [
            drift_finding_to_dict(finding) for finding in report.workflow_drift_findings
        ],
    }
