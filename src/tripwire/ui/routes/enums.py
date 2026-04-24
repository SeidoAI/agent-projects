"""Enum descriptor routes (KUI-32).

Single endpoint::

    GET /api/projects/{project_id}/enums/{name}  -> EnumDescriptor

The name regex uses underscores (not hyphens) to match the filename
convention used by existing projects (`issue_status.yaml`,
`agent_state.yaml`). No list-all endpoint in v1 — the frontend fetches
each enum on project-switch and caches for 5 minutes.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.enum_service import (
    EnumDescriptor,
)
from tripwire.ui.services.enum_service import (
    get_enum as svc_get_enum,
)

router = APIRouter(prefix="/api/projects/{project_id}/enums", tags=["enums"])

_NAME_PATTERN = r"^[a-z][a-z0-9_]*$"
_NAME_RE = re.compile(_NAME_PATTERN)


def _ensure_name(name: str) -> None:
    """Raise ``400 + envelope`` on a malformed name so the error shape
    matches every other ``/api/`` route."""
    if not _NAME_RE.match(name):
        raise envelope_exception(
            400,
            code="enum/bad_name",
            detail=(
                f"Enum name {name!r} does not match {_NAME_PATTERN} "
                "(lowercase letter first, then alphanumerics or underscores)."
            ),
        )


@router.get("/{name}", response_model=EnumDescriptor)
async def get_enum(
    name: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> EnumDescriptor:
    _ensure_name(name)
    try:
        return svc_get_enum(project.project_dir, name)
    except FileNotFoundError as exc:
        raise envelope_exception(
            404,
            code="enum/not_found",
            detail=f"Enum {name!r} not configured for this project.",
        ) from exc
