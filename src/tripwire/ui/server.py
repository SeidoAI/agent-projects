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
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as _StarletteHTTPException

import tripwire

logger = logging.getLogger("tripwire.ui.server")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown lifecycle for the Tripwire UI app.

    Startup: build the shared event queue, :class:`WebSocketHub`, file-watcher
    :class:`~watchdog.observers.Observer`, and background tasks
    (``broadcast_events`` + ``heartbeat_loop``), stashing handles on
    ``app.state`` for dependency access and clean shutdown.

    Shutdown: cancel the tasks (awaiting their cancellation), stop + join the
    observer, close every live WebSocket.
    """
    # Imports live here so unit tests that patch any of these modules see the
    # patched version at app-startup time.
    from tripwire.ui.file_watcher import start_watching
    from tripwire.ui.services.project_service import _project_id
    from tripwire.ui.ws.hub import (
        WebSocketHub,
        broadcast_events,
        heartbeat_loop,
    )

    # Startup ---------------------------------------------------------------
    event_queue: asyncio.Queue = asyncio.Queue()
    hub = WebSocketHub()

    project_dirs: list[Path] = list(getattr(app.state, "project_dirs", []) or [])
    project_tuples: list[tuple[str, Path]] = [
        (_project_id(Path(p).resolve()), Path(p)) for p in project_dirs
    ]
    loop = asyncio.get_running_loop()
    observer = start_watching(project_tuples, event_queue, loop)

    broadcaster = asyncio.create_task(
        broadcast_events(event_queue, hub), name="tripwire.ui.broadcaster"
    )
    heartbeat = asyncio.create_task(
        heartbeat_loop(hub), name="tripwire.ui.heartbeat"
    )

    app.state.event_queue = event_queue
    app.state.hub = hub
    app.state.observer = observer
    app.state.broadcaster_task = broadcaster
    app.state.heartbeat_task = heartbeat

    logger.info("Tripwire UI started")

    try:
        yield
    finally:
        # Shutdown ----------------------------------------------------------
        logger.info("Tripwire UI shutting down")

        for task in (broadcaster, heartbeat):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        observer.stop()
        # ``observer.join`` is blocking — offload so the event loop stays
        # responsive during shutdown.
        await asyncio.to_thread(observer.join)

        await hub.close_all()


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
        except _StarletteHTTPException as exc:
            if exc.status_code == 404:
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

    static_dir = Path(str(importlib.resources.files("tripwire.ui"))) / "static"

    if not (static_dir / "index.html").exists():
        logger.warning(
            "Frontend statics not found at %s — "
            "`pip install tripwire` ships the bundle, or run the Vite dev server.",
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
        handles it via its proxy config).
    """
    app = FastAPI(
        title="Tripwire UI",
        version=tripwire.__version__,
        lifespan=lifespan,
    )

    from tripwire.ui.routes import register_routes

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

    Called by the ``tripwire ui`` CLI command.
    """
    import uvicorn

    from tripwire.ui.services.project_service import seed_project_index

    app = create_app(dev_mode=dev_mode)
    app.state.project_dirs = project_dirs

    # Ensure the project index is populated even when discover_projects()
    # was not called (e.g. the --project-dir CLI path).
    seed_project_index(project_dirs)

    url = f"http://{host}:{port}"

    if open_browser and not dev_mode:
        threading.Timer(0.8, webbrowser.open, args=[url]).start()

    uvicorn.run(app, host=host, port=port, log_level="info")
