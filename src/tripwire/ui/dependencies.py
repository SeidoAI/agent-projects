"""FastAPI dependency injection — ``Depends()`` factories for routes.

``ProjectContext`` is the per-request typed container injected into every
project-scoped route via ``Depends(get_project)``.
"""

from __future__ import annotations

import asyncio
import functools
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi import Path as PathParam

from tripwire.core.store import ProjectNotFoundError, load_project
from tripwire.models.project import ProjectConfig
from tripwire.ui.services.project_service import get_project_dir

# ---------------------------------------------------------------------------
# ProjectContext
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectContext:
    """Per-request project binding.

    Holds the resolved project directory, its on-disk config, and the
    short hex id used in URL paths.  ``config.workspace`` exposes the
    optional workspace pointer for future workspace-aware routes.
    """

    project_id: str
    project_dir: Path
    config: ProjectConfig


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=64)
def _resolve_project_dir(project_id: str) -> Path | None:
    """Map a project id to its directory, cached across requests."""
    return get_project_dir(project_id)


def reset_project_cache() -> None:
    """Clear the ``_resolve_project_dir`` LRU cache (useful in tests)."""
    _resolve_project_dir.cache_clear()


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def get_project(
    project_id: str = PathParam(..., pattern=r"^[a-f0-9]{12}$"),
) -> ProjectContext:
    """Resolve a project from the URL path parameter.

    Raises
    ------
    HTTPException(404)
        Unknown project id.
    HTTPException(500)
        Project directory exists in the index but ``project.yaml`` is missing.
    """
    project_dir = _resolve_project_dir(project_id)
    if project_dir is None:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        config = load_project(project_dir)
    except ProjectNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail="project.yaml missing from project directory",
        ) from exc

    return ProjectContext(
        project_id=project_id,
        project_dir=project_dir,
        config=config,
    )


def get_hub(request: Request) -> Any | None:
    """Return the WebSocket hub from ``app.state`` (``None`` until KUI-37)."""
    return request.app.state.hub


def get_event_queue(request: Request) -> asyncio.Queue:
    """Return the shared event queue from ``app.state``."""
    return request.app.state.event_queue
