"""GitHub PR routes (v2 stub — 501 Not Implemented)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/github", tags=["github (v2)"])

_V2 = HTTPException(status_code=501, detail="Not implemented in v1")


@router.get("/prs")
async def list_prs() -> None:
    raise _V2


@router.get("/prs/{pr_number}/checks")
async def get_pr_checks(pr_number: int) -> None:
    raise _V2


@router.get("/prs/{pr_number}/reviews")
async def get_pr_reviews(pr_number: int) -> None:
    raise _V2
