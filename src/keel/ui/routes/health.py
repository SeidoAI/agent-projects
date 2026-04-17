"""Health-check endpoint.

NOTE: This endpoint was added outside the KUI-12 spec (which listed 14
routers, not 15). A formal issue should be created to document it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple health check."""
    return {"status": "ok"}
