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
import tempfile
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
        "name: e2e\nkey_prefix: E2E\nnext_issue_number: 1\nnext_session_number: 1\n",
        encoding="utf-8",
    )
    for sub in ("issues", "nodes", "sessions", "docs"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="module")
def tripwire_ui_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict]:
    project_dir = _make_minimal_project(tmp_path_factory.mktemp("e2e_proj"))
    port = _free_port()

    # Subprocess output goes to a tempfile (not subprocess.PIPE) so
    # uvicorn's startup chatter can't fill the ~64KB OS pipe buffer
    # and block the child on write — that failure would surface as a
    # 30s readiness timeout instead of the actual cause. The file is
    # only read on the unhappy path (early exit or readiness timeout).
    log_file = tempfile.NamedTemporaryFile(
        prefix="tripwire-ui-e2e-", suffix=".log", delete=False
    )

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
        stdout=log_file,
        stderr=subprocess.STDOUT,
        cwd=str(project_dir),
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
    )

    def _read_log() -> str:
        log_file.flush()
        try:
            return Path(log_file.name).read_text(errors="replace")
        except OSError:
            return "<log file unreadable>"

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 30.0
    last_err: Exception | None = None
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"tripwire ui exited early with code {proc.returncode}\n"
                f"--- subprocess log ---\n{_read_log()}"
            )
        try:
            r = httpx.get(f"{base_url}/api/health", timeout=1.0)
            if r.status_code == 200:
                ready = True
                break
        except httpx.HTTPError as exc:
            last_err = exc
        time.sleep(0.2)

    if not ready:
        proc.terminate()
        raise RuntimeError(
            f"tripwire ui did not become ready in 30s (last err: {last_err!r})\n"
            f"--- subprocess log ---\n{_read_log()}"
        )

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
        log_file.close()
        try:
            os.unlink(log_file.name)
        except OSError:
            pass
