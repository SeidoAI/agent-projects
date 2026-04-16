"""FastAPI application factory and uvicorn launcher.

``create_app`` builds the FastAPI instance (lifespan, routes, static mount).
``start_server`` is the entrypoint called by the CLI.
"""

from __future__ import annotations

import asyncio
import importlib.resources
import logging
import threading
import webbrowser
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import keel

logger = logging.getLogger("keel.ui.server")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle for the Keel UI app.

    Startup: initialise shared state on ``app.state``.
    Shutdown: cancel any background tasks attached to ``app.state``.
    """
    # Startup
    app.state.event_queue = asyncio.Queue()
    app.state.hub = None  # WebSocket hub — wired by KUI-37
    app.state.observer = None  # File-watcher observer — wired by KUI-36
    logger.info("Keel UI started")

    yield

    # Shutdown
    logger.info("Keel UI shutting down")


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------


class _SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to ``index.html`` for unknown paths.

    This gives React Router (or any SPA) control over client-side routing:
    ``/some/deep/path`` returns ``index.html`` instead of 404.
    """

    async def get_response(self, path: str, scope: object) -> object:  # type: ignore[override]
        try:
            return await super().get_response(path, scope)
        except Exception as exc:
            # Starlette raises HTTPException(404) for missing files.
            if getattr(exc, "status_code", None) == 404:
                return await super().get_response(".", scope)
            raise


def _mount_static(app: FastAPI, *, dev_mode: bool) -> None:
    """Mount the React static bundle at ``/`` (prod) or skip (dev).

    Must be called AFTER ``register_routes`` so that ``/api/*`` routes take
    precedence over the catch-all static mount.
    """
    if dev_mode:
        logger.info(
            "Dev mode — expecting Vite at http://localhost:3000 "
            "with /api proxy configured."
        )
        return

    static_dir = Path(str(importlib.resources.files("keel.ui"))) / "static"

    if not (static_dir / "index.html").exists():
        logger.warning(
            "Frontend statics not found at %s — "
            "`pip install keel` ships the bundle, or run the Vite dev server.",
            static_dir,
        )
        return

    app.mount(
        "/",
        _SPAStaticFiles(directory=static_dir, html=True, check_dir=False),
        name="static",
    )
    logger.info("Serving static files from %s", static_dir)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(*, dev_mode: bool = False) -> FastAPI:
    """Build and return the FastAPI application.

    Parameters
    ----------
    dev_mode:
        When ``True``, skip the static file mount (the Vite dev server
        handles it) and enable CORS for the dev proxy.
    """
    app = FastAPI(
        title="Keel UI",
        version=keel.__version__,
        lifespan=lifespan,
    )

    from keel.ui.routes import register_routes

    register_routes(app)

    _mount_static(app, dev_mode=dev_mode)

    return app


# ---------------------------------------------------------------------------
# Server launcher
# ---------------------------------------------------------------------------


def start_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    project_dirs: list[Path],
    dev_mode: bool = False,
    open_browser: bool = True,
) -> None:
    """Create the app and run it under uvicorn.

    Called by the ``keel ui`` CLI command.
    """
    import uvicorn

    from keel.ui.services.project_service import seed_project_index

    app = create_app(dev_mode=dev_mode)
    app.state.project_dirs = project_dirs

    # Ensure the project index is populated even when discover_projects()
    # was not called (e.g. the --project-dir CLI path).
    seed_project_index(project_dirs)

    url = f"http://{host}:{port}"

    if open_browser and not dev_mode:
        threading.Timer(0.8, webbrowser.open, args=[url]).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
