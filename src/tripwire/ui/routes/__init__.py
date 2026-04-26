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

    Also installs the shared v1 error-envelope exception handler so
    routes can raise via :func:`_common.envelope_exception` and have the
    body serialised as ``{detail, code, hint?}`` at the top level.
    """
    from tripwire.ui.routes import (
        _common,
        actions,
        artifacts,
        containers,
        enums,
        events,
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

    _common.install_error_handlers(app)

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
        events,
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
