"""Global action routes (validate, rebuild-index, advance-phase, finalize-session).

Endpoints implemented in KUI-34.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.post("/validate")
async def validate(body: dict) -> dict:
    """Run project validation."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
