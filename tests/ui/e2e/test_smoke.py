"""Cross-stack smoke tests — boot the real CLI/server and hit the API.

These intentionally exercise the full surface (CLI -> uvicorn ->
FastAPI -> services -> filesystem -> WebSocket) on every run. Mocks
are appropriate elsewhere; this suite is the only place the wire
itself is asserted.

Marked ``e2e`` so they're opt-in via ``pytest -m e2e``; the default
test run skips them via the ``addopts = "... -m 'not e2e'"`` filter
in ``pyproject.toml``.
"""

from __future__ import annotations

import asyncio
from importlib.resources import files

import httpx
import pytest
import websockets

pytestmark = pytest.mark.e2e


def _static_bundle_present() -> bool:
    """Check whether the React build artefact is on disk.

    The root route only returns 200 when the bundle has been built
    (`npm run build` writes to `src/tripwire/ui/static/`). The other
    three smoke tests are independent of the bundle.
    """
    static_dir = files("tripwire.ui").joinpath("static")
    return static_dir.joinpath("index.html").is_file()  # type: ignore[no-any-return]


def test_root_serves_spa_when_bundle_built(tripwire_ui_server: dict) -> None:
    if not _static_bundle_present():
        pytest.skip("React static bundle not built — run `npm run build` in web")
    r = httpx.get(tripwire_ui_server["base_url"] + "/", timeout=5.0)
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")


def test_get_projects_returns_seeded_project(tripwire_ui_server: dict) -> None:
    r = httpx.get(tripwire_ui_server["base_url"] + "/api/projects", timeout=5.0)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    project = next(
        (
            item
            for item in body
            if item["dir"] == str(tripwire_ui_server["project_dir"])
        ),
        None,
    )
    assert project is not None
    assert project["name"] == "e2e"
    assert project["key_prefix"] == "E2E"
    # ID is a 12-char hex hash of the project dir.
    assert isinstance(project["id"], str) and len(project["id"]) == 12


def test_get_issues_returns_empty_list(tripwire_ui_server: dict) -> None:
    base = tripwire_ui_server["base_url"]
    projects = httpx.get(f"{base}/api/projects", timeout=5.0).json()
    pid = projects[0]["id"]
    r = httpx.get(f"{base}/api/projects/{pid}/issues", timeout=5.0)
    assert r.status_code == 200
    # Fresh project -> no issue files -> empty list.
    assert r.json() == []


def test_websocket_accepts_connection(tripwire_ui_server: dict) -> None:
    base = tripwire_ui_server["base_url"]
    projects = httpx.get(f"{base}/api/projects", timeout=5.0).json()
    pid = projects[0]["id"]
    ws_url = f"ws://127.0.0.1:{tripwire_ui_server['port']}/api/ws?project={pid}"

    async def _connect_and_close() -> None:
        async with websockets.connect(ws_url, open_timeout=5.0) as ws:
            assert ws.state.name == "OPEN"

    asyncio.run(_connect_and_close())
