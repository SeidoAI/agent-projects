"""Keel UI backend — FastAPI server, routes, services, and WebSocket hub.

This package provides the web dashboard for browsing and managing keel
projects. Heavy dependencies (FastAPI, uvicorn, watchdog) are imported
lazily inside submodules so that ``import keel.ui`` works even on a
minimal ``keel[projects]`` install.
"""

__all__: list[str] = []
