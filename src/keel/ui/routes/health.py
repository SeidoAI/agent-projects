"""Health-check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple health check."""
    return {"status": "ok"}
