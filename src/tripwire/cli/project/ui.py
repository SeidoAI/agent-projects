"""`tripwire project ui` — start the Tripwire dashboard.

Heavy imports (FastAPI, uvicorn) happen inside the command body so that
``tripwire --help`` works even on a minimal ``tripwire[projects]`` install.
"""

from __future__ import annotations

import http.client
import json
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import click

from tripwire.cli.project._group import project_cmd

# Modules whose absence indicates a minimal [projects] install.
_UI_MODULES = frozenset({"fastapi", "uvicorn", "watchdog", "websockets"})

# Single-instance probe: GET timeout (seconds).
_PROBE_TIMEOUT = 0.5


def _find_project_root(start: Path) -> Path | None:
    """Walk up from *start* looking for a directory containing ``project.yaml``."""
    for candidate in (start, *start.parents):
        if (candidate / "project.yaml").is_file():
            return candidate
    return None


def _check_port(host: str, port: int) -> tuple[str, str]:
    """Probe ``/api/health`` to detect an already-running tripwire instance.

    Returns one of:

    * ``("free", url)`` — connection refused / timeout / non-HTTP response.
      The caller can bind on this port.
    * ``("reuse", url)`` — port answers and the response is a tripwire
      health payload. The caller should open the URL and exit instead of
      double-binding.
    * ``("conflict", url)`` — port answers but is not a tripwire instance.
      The caller should fail loudly so the user picks a different port.
    """
    url = f"http://{host}:{port}"
    try:
        with urllib.request.urlopen(
            f"{url}/api/health", timeout=_PROBE_TIMEOUT
        ) as response:
            body = response.read().decode("utf-8")
    except (
        urllib.error.URLError,
        TimeoutError,
        ConnectionError,
        OSError,
        # `http.client.HTTPException` (and its subclasses
        # `RemoteDisconnected`, `IncompleteRead`, `BadStatusLine`) does
        # not inherit from `OSError` or `URLError`. Without it, a server
        # that closes the connection mid-response (race during shutdown,
        # mismatched HTTP version, etc.) crashes the CLI instead of
        # returning a verdict.
        http.client.HTTPException,
    ):
        return ("free", url)

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return ("conflict", url)

    if isinstance(payload, dict) and payload.get("service") == "tripwire":
        return ("reuse", url)
    return ("conflict", url)


@project_cmd.command(name="ui")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help="Open directly to this project [default: auto-discover].",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    show_default=True,
    help="HTTP port.",
)
@click.option(
    "--no-browser",
    is_flag=True,
    help="Don't auto-open the browser.",
)
@click.option(
    "--dev",
    is_flag=True,
    help="Dev mode (expects Vite on :3000 proxying /api).",
)
def ui_cmd(
    project_dir: Path | None,
    port: int,
    no_browser: bool,
    dev: bool,
) -> None:
    """Start the Tripwire dashboard (localhost only)."""
    # 1. Import check — graceful degradation on minimal installs.
    try:
        from tripwire.ui.server import start_server
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "") or ""
        if any(mod in missing for mod in _UI_MODULES):
            click.echo(
                "The UI requires the full tripwire install.\n"
                "Run:\n"
                "  pip install tripwire-pm\n"
                "(You appear to have tripwire-pm[projects] "
                "— a minimal install without web deps.)"
            )
            sys.exit(1)
        raise

    # 2. Load user config.
    from tripwire.ui.config import load_user_config

    config = load_user_config()

    # 3. Resolve project directories.
    #
    # `pin` controls whether the resolved project_dirs *restrict* discovery
    # (the --project-dir case — user explicitly scoped this run to one
    # project) or merely *augment* it (cwd / wide-discovery cases — the
    # user wants the dropdown to show everything they have).
    from tripwire.ui.services.project_service import discover_projects

    if project_dir is not None:
        project_dirs = [project_dir.expanduser().resolve()]
        pin = True
    else:
        # Wide discovery first — surfaces every project under
        # `config.project_roots` and the fallback locations.
        discovered = discover_projects(config)
        project_dirs = [Path(p.dir) for p in discovered]

        # Augment with cwd's project if we're inside one and it didn't
        # already show up in discovery.
        cwd_project = _find_project_root(Path.cwd())
        if cwd_project is not None:
            cwd_resolved = cwd_project.resolve()
            if cwd_resolved not in {p.resolve() for p in project_dirs}:
                project_dirs.append(cwd_resolved)

        if not project_dirs:
            # No projects found anywhere — still launch the UI so the
            # user can see the empty state and take action (e.g. open
            # another project from the picker route, or add a project
            # root via `tripwire project config add`). Killing the launch here
            # would leave them with nothing actionable in the terminal.
            click.echo(
                "No projects discovered. Launching UI anyway —\n"
                "use the picker or `tripwire project config add project-root <path>`\n"
                "to register one."
            )
        pin = False

    # 4. Single-instance probe: if a tripwire UI is already on this port,
    #    open the existing instance instead of double-binding. Skipped in
    #    dev mode (Vite proxies /api but no tripwire is listening yet).
    host = "127.0.0.1"
    if not dev:
        verdict, existing_url = _check_port(host, port)
        if verdict == "reuse":
            click.echo(f"Tripwire UI is already running at {existing_url}")
            if not no_browser:
                webbrowser.open(existing_url)
            return
        if verdict == "conflict":
            click.echo(
                f"Port {port} is in use by another service "
                f"(not a tripwire UI). Pick a different --port.",
                err=True,
            )
            sys.exit(1)

    # 5. Launch the server.
    start_server(
        host=host,
        port=port,
        project_dirs=project_dirs,
        dev_mode=dev,
        open_browser=not no_browser,
        pin=pin,
    )
