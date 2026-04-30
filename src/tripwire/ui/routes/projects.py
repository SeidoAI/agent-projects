"""Project listing and detail routes (KUI-26).

Read-only endpoints. Both are thin wrappers over
:mod:`tripwire.ui.services.project_service`; translation of service
exceptions to HTTP status codes happens here, nothing else.
"""

from __future__ import annotations

from fastapi import APIRouter, Path

from tripwire.ui.routes._common import envelope_exception
from pydantic import BaseModel

from tripwire.ui.services.project_service import (
    ProjectDetail,
    ProjectSummary,
    find_project_by_identity,
    get_project,
    list_projects,
)

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("", response_model=list[ProjectSummary])
async def list_all_projects() -> list[ProjectSummary]:
    """Return every discoverable project as a :class:`ProjectSummary`."""
    return list_projects()


class _FindBody(BaseModel):
    name: str
    key_prefix: str


@router.post("/find", response_model=ProjectSummary)
async def find_project(body: _FindBody) -> ProjectSummary:
    """Locate a project by its ``name`` + ``key_prefix`` identity.

    Used by the frontend folder-picker: the user selects a project directory,
    the UI reads ``project.yaml`` to extract these two fields, then calls this
    endpoint to get the project id for navigation.
    """
    try:
        return find_project_by_identity(body.name, body.key_prefix)
    except KeyError as exc:
        raise envelope_exception(
            404,
            code="project/not_found",
            detail=f"No project found with name={body.name!r} and key_prefix={body.key_prefix!r}",
        ) from exc


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project_detail(
    project_id: str = Path(..., pattern=r"^[a-f0-9]{12}$"),
) -> ProjectDetail:
    """Return full :class:`ProjectDetail` for *project_id*.

    Translates :class:`KeyError` from the service (unknown project id)
    to a 404 envelope with code ``project/not_found``.
    """
    try:
        return get_project(project_id)
    except KeyError as exc:
        raise envelope_exception(
            404,
            code="project/not_found",
            detail=f"Project {project_id!r} not found",
        ) from exc
