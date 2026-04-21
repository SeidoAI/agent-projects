"""Global action routes (validate, rebuild-index, advance-phase, finalize-session).

Endpoints filled by their respective route issues.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/actions", tags=["actions"])

# Replace these 501 stubs when implementing the real endpoints.


@router.post("/validate")
async def validate() -> None:
    """Run project validation."""
    raise HTTPException(status_code=501, detail="Not yet implemented")
