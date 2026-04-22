"""Artifact manifest + per-session artifact routes (KUI-31).

Five endpoints under `/api/projects/{project_id}`:

    GET   /artifact-manifest
    GET   /sessions/{sid}/artifacts
    GET   /sessions/{sid}/artifacts/{name}
    POST  /sessions/{sid}/artifacts/{name}/approve
    POST  /sessions/{sid}/artifacts/{name}/reject

Approve/reject bodies are modelled via Pydantic so OpenAPI picks them
up. Reject requires a non-empty ``feedback`` string; approve accepts an
optional one. Ungated artifacts reject both ops with 409 — a silent
no-op would mask a UI misconfiguration.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.artifact_service import (
    ArtifactContent,
    ArtifactManifest,
    ArtifactStatus,
    approve_artifact,
    get_manifest,
    get_session_artifact,
    reject_artifact,
)
from tripwire.ui.services.artifact_service import (
    list_session_artifacts as svc_list_session_artifacts,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["artifacts"])


class ApproveBody(BaseModel):
    """Optional reviewer note attached to an approval."""

    feedback: str | None = None


class RejectBody(BaseModel):
    """Required reviewer note explaining the rejection."""

    feedback: str = Field(..., description="Non-empty reviewer note.")


@router.get("/artifact-manifest", response_model=ArtifactManifest)
async def get_artifact_manifest(
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ArtifactManifest:
    return get_manifest(project.project_dir)


@router.get(
    "/sessions/{sid}/artifacts",
    response_model=list[ArtifactStatus],
)
async def list_session_artifacts(
    sid: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> list[ArtifactStatus]:
    return svc_list_session_artifacts(project.project_dir, sid)


@router.get(
    "/sessions/{sid}/artifacts/{name}",
    response_model=ArtifactContent,
)
async def get_artifact(
    sid: str,
    name: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ArtifactContent:
    try:
        return get_session_artifact(project.project_dir, sid, name)
    except FileNotFoundError as exc:
        raise envelope_exception(
            404,
            code="artifact/not_found",
            detail=f"Artifact {name!r} not found in session {sid!r}.",
        ) from exc


@router.post(
    "/sessions/{sid}/artifacts/{name}/approve",
    response_model=ArtifactStatus,
)
async def approve(
    sid: str,
    name: str,
    body: ApproveBody = ApproveBody(),  # noqa: B008
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ArtifactStatus:
    try:
        return approve_artifact(project.project_dir, sid, name, feedback=body.feedback)
    except ValueError as exc:
        raise envelope_exception(
            409,
            code="artifact/no_gate",
            detail=str(exc),
        ) from exc


@router.post(
    "/sessions/{sid}/artifacts/{name}/reject",
    response_model=ArtifactStatus,
)
async def reject(
    sid: str,
    name: str,
    body: RejectBody,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ArtifactStatus:
    try:
        return reject_artifact(project.project_dir, sid, name, feedback=body.feedback)
    except ValueError as exc:
        # Empty feedback and "no gate configured" both land here.
        raise envelope_exception(
            409,
            code="artifact/no_gate",
            detail=str(exc),
        ) from exc
