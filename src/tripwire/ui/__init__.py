"""Tripwire UI backend — FastAPI server, routes, services, and WebSocket hub.

This package provides the web dashboard for browsing and managing tripwire
projects. Heavy dependencies (FastAPI, uvicorn, watchdog) are imported
lazily inside submodules so that ``import tripwire.ui`` works even on a
minimal ``tripwire[projects]`` install.
"""

__all__: list[str] = []
