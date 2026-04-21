"""FastAPI route modules — one file per resource, registered in server.py."""

from __future__ import annotations

import logging
from types import ModuleType

from fastapi import FastAPI

logger = logging.getLogger("tripwire.ui.routes")


def register_routes(app: FastAPI) -> None:
    """Import every route module and include its router on *app*.

    Called by ``create_app`` before the static-file mount so that ``/api/*``
    routes take precedence over the catch-all ``StaticFiles`` mount.
    """
    from tripwire.ui.routes import (
        actions,
        artifacts,
        containers,
        enums,
        github,
        graph,
        health,
        issues,
        messages,
        nodes,
        orchestration,
        pm_reviews,
        projects,
        sessions,
        ws,
    )

    modules: list[ModuleType] = [
        health,
        projects,
        issues,
        nodes,
        graph,
        sessions,
        artifacts,
        enums,
        orchestration,
        actions,
        ws,
        # v2 stubs
        messages,
        github,
        containers,
        pm_reviews,
    ]

    count = 0
    for mod in modules:
        if hasattr(mod, "router"):
            app.include_router(mod.router)
            count += 1

    logger.info("Registered %d route module(s)", count)
