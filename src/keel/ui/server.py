"""FastAPI application factory and uvicorn launcher.

TODO: Implement in KUI-9 — creates the FastAPI app, mounts static files,
registers route modules, and starts the uvicorn server.
"""

from __future__ import annotations

from pathlib import Path


def start_server(
    *,
    host: str,
    port: int,
    project_dirs: list[Path],
    dev_mode: bool,
    open_browser: bool,
) -> None:
    """Start the uvicorn server. Implemented in KUI-9."""
    raise NotImplementedError("Server not yet implemented — see KUI-9.")
