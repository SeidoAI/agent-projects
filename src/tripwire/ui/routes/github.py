"""GitHub PR routes (v2 stub — 501 Not Implemented).

Every endpoint returns 501 via the shared ``raise_v2_not_implemented``
helper. DTOs are declared on :mod:`tripwire.ui.services.github_service`
so OpenAPI lists realistic shapes for frontend type generation.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from fastapi import APIRouter

from tripwire.ui.routes._v2_stub import raise_v2_not_implemented
from tripwire.ui.services.github_service import (
    CheckRun,
    PRSummary,
    Review,
)

router = APIRouter(prefix="/api/github", tags=["github (v2)"])

_DETAIL = "github integration requires the v2 gh-CLI wrapper (not yet implemented)"


@router.get("/prs", response_model=list[PRSummary])
async def list_prs(repo: str, head: str | None = None) -> list[PRSummary]:
    raise_v2_not_implemented(_DETAIL)


@router.get("/prs/{pr_number}/checks", response_model=list[CheckRun])
async def get_pr_checks(pr_number: int, repo: str) -> list[CheckRun]:
    raise_v2_not_implemented(_DETAIL)


@router.get("/prs/{pr_number}/reviews", response_model=list[Review])
async def get_pr_reviews(pr_number: int, repo: str) -> list[Review]:
    raise_v2_not_implemented(_DETAIL)
