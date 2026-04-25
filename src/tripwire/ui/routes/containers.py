"""Container management routes (v2 stub — 501 Not Implemented).

Every endpoint returns 501 via the shared ``raise_v2_not_implemented``
helper. DTOs are declared on :mod:`tripwire.ui.services.container_service`
so OpenAPI lists realistic response shapes for frontend type generation.

See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from fastapi import APIRouter

from tripwire.ui.routes._v2_stub import V2_RESPONSES, raise_v2_not_implemented
from tripwire.ui.services.container_service import (
    CleanupResult,
    ContainerInfo,
    ContainerStats,
    LaunchRequest,
    LaunchResponse,
    LogTail,
    TerminalSession,
)

router = APIRouter(prefix="/api/containers", tags=["containers (v2)"])

_DETAIL = "containers feature requires tripwire.containers (v2 — not yet implemented)"


@router.get("", response_model=list[ContainerInfo], responses=V2_RESPONSES)
async def list_containers() -> list[ContainerInfo]:
    raise_v2_not_implemented(_DETAIL)


@router.get(
    "/{container_id}/stats", response_model=ContainerStats, responses=V2_RESPONSES
)
async def get_container_stats(container_id: str) -> ContainerStats:
    raise_v2_not_implemented(_DETAIL)


@router.get("/{container_id}/logs", response_model=LogTail, responses=V2_RESPONSES)
async def get_container_logs(container_id: str, tail: int = 50) -> LogTail:
    raise_v2_not_implemented(_DETAIL)


@router.post("/launch", response_model=LaunchResponse, responses=V2_RESPONSES)
async def launch_container(body: LaunchRequest) -> LaunchResponse:
    raise_v2_not_implemented(_DETAIL)


@router.post("/{container_id}/stop", responses=V2_RESPONSES)
async def stop_container(container_id: str) -> None:
    raise_v2_not_implemented(_DETAIL)


@router.post(
    "/{container_id}/terminal", response_model=TerminalSession, responses=V2_RESPONSES
)
async def open_container_terminal(container_id: str) -> TerminalSession:
    raise_v2_not_implemented(_DETAIL)


@router.post("/cleanup", response_model=CleanupResult, responses=V2_RESPONSES)
async def cleanup_containers() -> CleanupResult:
    raise_v2_not_implemented(_DETAIL)
