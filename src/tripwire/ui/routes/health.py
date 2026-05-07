"""Health-check endpoint.

NOTE: This endpoint was added outside the KUI-12 spec (which listed 14
routers, not 15). A formal issue should be created to document it.

Beyond liveness, the response carries a service signature so the
single-instance probe in ``tripwire.cli.ui`` can distinguish a running
tripwire UI from any other service that happens to be on the configured
port.
"""

from __future__ import annotations

from fastapi import APIRouter

import tripwire

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return a simple health check with service identity."""
    return {
        "status": "ok",
        "service": "tripwire",
        "version": tripwire.__version__,
    }
