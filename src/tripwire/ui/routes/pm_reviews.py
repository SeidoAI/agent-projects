"""PM review routes (v2 stub — 501 Not Implemented).

Project-scoped: ``/api/projects/{project_id}/pm-reviews``. The
``get_project`` dependency runs first, so unknown project ids return
404 before the 501 is raised — keeping the error envelope consistent
across the API.

DTOs live on :mod:`tripwire.ui.services.pm_review_service` so OpenAPI
lists realistic shapes for frontend type generation.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._v2_stub import raise_v2_not_implemented
from tripwire.ui.services.pm_review_service import (
    PmReviewDetail,
    PmReviewSummary,
)

router = APIRouter(
    prefix="/api/projects/{project_id}/pm-reviews",
    tags=["pm-reviews (v2)"],
)

_DETAIL = (
    "pm-reviews feature requires tripwire.containers orchestration "
    "(v2 — not yet implemented)"
)


@router.get("", response_model=list[PmReviewSummary])
async def list_pm_reviews(
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> list[PmReviewSummary]:
    raise_v2_not_implemented(_DETAIL)


@router.get("/{pr_number}", response_model=PmReviewDetail)
async def get_pm_review(
    pr_number: int,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> PmReviewDetail:
    raise_v2_not_implemented(_DETAIL)


@router.post("/{pr_number}/run", response_model=PmReviewDetail)
async def run_pm_review(
    pr_number: int,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> PmReviewDetail:
    raise_v2_not_implemented(_DETAIL)
