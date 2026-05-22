"""``tripwire session summary`` — summarise the latest spawn-attempt log."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli.session._group import session_cmd
from tripwire.cli.session._helpers import _resolve_and_load_session


@session_cmd.command("summary")
@click.argument("session_id")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
)
def session_summary_cmd(
    session_id: str,
    project_dir: Path,
    output_format: str,
) -> None:
    """Summarise the latest spawn attempt for a session.

    Parses the most recent stream-json log file into a readable
    shape: claude session uuid, exit subtype, tool-call count, token
    usage, and the final assistant text. Flags sessions that
    "stopped to ask" (clean exit whose final text contains a
    question).
    """
    import dataclasses
    import json as _json

    from tripwire.core.session_log_parser import format_text, parse

    _, session = _resolve_and_load_session(project_dir, session_id)

    log_path_str = session.runtime_state.log_path
    if not log_path_str:
        raise click.ClickException(
            f"session '{session_id}' has no recorded log_path — "
            "the session may never have been spawned."
        )
    latest_log = Path(log_path_str).expanduser()
    log_dir = latest_log.parent
    matches = sorted(log_dir.glob(f"{session_id}-*.log")) if log_dir.is_dir() else []
    if not matches and latest_log.is_file():
        matches = [latest_log]
    if not matches:
        raise click.ClickException(f"no log files found for session '{session_id}'")

    summary = parse(matches[-1])
    if output_format == "json":
        payload = dataclasses.asdict(summary)
        payload["log_path"] = str(summary.log_path)
        click.echo(_json.dumps(payload, indent=2))
    else:
        click.echo(format_text(summary))
