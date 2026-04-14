"""`keel session` — read-only operations on agent sessions.

Sessions live at `sessions/<id>/session.yaml`. In v0 agents write session
files directly; the CLI provides only browsing.

Subcommands:
- `list` — enumerate all sessions with status and issue counts
- `show <id>` — print one session's full YAML frontmatter + body
- `artifacts <id>` — alias for `keel artifacts list <id>`
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from keel.cli._utils import require_project as _require_project
from keel.cli.artifacts import artifacts_list
from keel.core.session_store import list_sessions, load_session

console = Console()


@dataclass
class SessionSummary:
    id: str
    name: str
    agent: str
    status: str
    issue_count: int
    repo_count: int


@click.group(name="session")
def session_cmd() -> None:
    """Session operations (read-only in v0)."""


@session_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
def session_list_cmd(project_dir: Path, output_format: str) -> None:
    """List every session in the project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    summaries = [
        SessionSummary(
            id=s.id,
            name=s.name,
            agent=s.agent,
            status=s.status,
            issue_count=len(s.issues),
            repo_count=len(s.repos),
        )
        for s in sessions
    ]

    if output_format == "json":
        click.echo(json.dumps([asdict(s) for s in summaries], indent=2))
        return

    if not summaries:
        console.print("[dim]no sessions yet[/dim]")
        return

    table = Table(title="Sessions", show_header=True)
    table.add_column("id")
    table.add_column("name")
    table.add_column("agent")
    table.add_column("status")
    table.add_column("issues", justify="right")
    table.add_column("repos", justify="right")
    for s in summaries:
        table.add_row(
            s.id,
            s.name,
            s.agent,
            s.status,
            str(s.issue_count),
            str(s.repo_count),
        )
    console.print(table)


@session_cmd.command("show")
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
def session_show_cmd(session_id: str, project_dir: Path, output_format: str) -> None:
    """Print one session's YAML (text) or structured data (json)."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(session.model_dump_json(indent=2, exclude_none=True))
        return

    from keel.core.session_store import session_yaml_path

    yaml_path = session_yaml_path(resolved, session_id)
    click.echo(yaml_path.read_text(encoding="utf-8"))


# Alias `keel session artifacts <id>` to the existing `keel artifacts list <id>`.
# Exposes session-related commands in one place instead of making users
# remember that artifact browsing sits under a separate top-level command.
session_cmd.add_command(artifacts_list, name="artifacts")
