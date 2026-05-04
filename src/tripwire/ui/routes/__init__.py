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
        drift,
        enums,
        events,
        graph,
        health,
        inbox,
        issues,
        nodes,
        orchestration,
        projects,
        sessions,
        source,
        workflow,
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
        inbox,
        artifacts,
        enums,
        orchestration,
        actions,
        events,
        workflow,
        drift,
        source,
        ws,
    ]

    count = 0
    for mod in modules:
        if hasattr(mod, "router"):
            app.include_router(mod.router)
            count += 1

    logger.info("Registered %d route module(s)", count)
