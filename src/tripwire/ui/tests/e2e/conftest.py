"""Shared fixtures for the cross-stack e2e smoke suite.

The fixture below boots ``tripwire ui`` as a real subprocess on an
OS-allocated port, pointed at a minimal disposable project, and yields
``{host, port, process, project_dir}``. Teardown terminates the
subprocess (SIGTERM, then SIGKILL after a 5s grace) so no zombies
linger between test modules.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest


def _free_port() -> int:
    """Return an OS-assigned free TCP port on 127.0.0.1.

    There's a slight race between closing the socket and the CLI
    binding the same port, but it's acceptable for a single-machine
    test fixture.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_minimal_project(root: Path) -> Path:
    """Write the smallest valid tripwire project directory at *root*."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.yaml").write_text(
        "name: e2e\n"
        "key_prefix: E2E\n"
        "next_issue_number: 1\n"
        "next_session_number: 1\n",
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions", "docs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="module")
def tripwire_ui_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    project_dir = _make_minimal_project(tmp_path_factory.mktemp("e2e_proj"))
    port = _free_port()

    # Invoke via the current interpreter's `-m` so the test always uses
    # the in-tree code, not whatever `tripwire` may resolve to on PATH.
    #
    # `cwd=project_dir`: the CLI's `--project-dir` flag only seeds the
    # in-process project_index used by `get_project_dir()`; it does NOT
    # appear in the `/api/projects` listing (that endpoint calls
    # `discover_projects()` which walks CWD + configured project roots).
    # Running the subprocess from inside the project dir means the
    # depth-1 CWD scan picks it up, so listing + lookup agree on the
    # one project that exists.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tripwire.cli.main",
            "ui",
            "--port",
            str(port),
            "--no-browser",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(project_dir),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30.0
    last_err: Exception | None = None
    while time.time() < deadline:
        if proc.poll() is not None:
            output = (proc.stdout.read() if proc.stdout else b"").decode(errors="replace")
            raise RuntimeError(
                f"tripwire ui exited early with code {proc.returncode}\n--- output ---\n{output}"
            )
        try:
            r = httpx.get(f"{base_url}/api/health", timeout=1.0)
            if r.status_code == 200:
                break
        except httpx.HTTPError as exc:
            last_err = exc
        time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError(f"tripwire ui did not become ready in 30s (last err: {last_err!r})")

    try:
        yield {
            "host": "127.0.0.1",
            "port": port,
            "process": proc,
            "project_dir": project_dir,
            "base_url": base_url,
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
