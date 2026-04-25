"""Container service placeholder (v2 stub).

The v2 implementation will live in ``tripwire.containers`` and wrap the
Docker SDK. This module declares the DTO shapes referenced by the v2
route OpenAPI schema so the frontend's generated client has realistic
types, and a ``ContainerService`` whose every method raises
``NotImplementedError``.

No Docker SDK imports live here — the stub is API-shape only.
See [[dec-v2-stubs-not-deferred]].
"""

from __future__ import annotations

from pydantic import BaseModel

_NI_MESSAGE = (
    "tripwire.containers is not yet implemented (v2). See docs/agent-containers.md."
)


# ---------------------------------------------------------------------------
# DTOs (OpenAPI-only; never returned in v1)
# ---------------------------------------------------------------------------


class ContainerInfo(BaseModel):
    """Summary of a running container."""

    id: str
    name: str
    image: str
    status: str
    session_id: str | None = None
    project_id: str | None = None


class ContainerStats(BaseModel):
    """Point-in-time container resource usage."""

    id: str
    cpu_percent: float
    memory_bytes: int
    memory_limit_bytes: int


class LogTail(BaseModel):
    """Tail of container stdout/stderr."""

    id: str
    lines: list[str]


class LaunchRequest(BaseModel):
    """Request body for ``POST /api/containers/launch``."""

    session_id: str
    project_id: str


class LaunchResponse(BaseModel):
    """Result of launching a container."""

    container_id: str


class TerminalSession(BaseModel):
    """Handle returned when attaching a terminal to a container."""

    container_id: str
    ws_url: str


class CleanupResult(BaseModel):
    """Summary of a bulk cleanup pass."""

    removed: int


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ContainerService:
    """Placeholder container service.

    Every method raises :class:`NotImplementedError`; the v2 implementation
    lands in ``tripwire.containers``.
    """

    def list_running(self) -> list[ContainerInfo]:
        raise NotImplementedError(_NI_MESSAGE)

    def get_stats(self, container_id: str) -> ContainerStats:
        raise NotImplementedError(_NI_MESSAGE)

    def get_logs(self, container_id: str, tail: int = 50) -> LogTail:
        raise NotImplementedError(_NI_MESSAGE)

    def launch(self, session_id: str, project_id: str) -> LaunchResponse:
        raise NotImplementedError(_NI_MESSAGE)

    def stop(self, container_id: str) -> None:
        raise NotImplementedError(_NI_MESSAGE)

    def terminal(self, container_id: str) -> TerminalSession:
        raise NotImplementedError(_NI_MESSAGE)

    def cleanup(self) -> CleanupResult:
        raise NotImplementedError(_NI_MESSAGE)
