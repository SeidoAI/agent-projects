"""``tripwire session show`` — print one session's full YAML/JSON."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.session_store import load_session


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
@click.option(
    "--full",
    "full",
    is_flag=True,
    default=False,
    help=(
        "Expand self-review.md and pm-response.yaml inline. Default "
        "shows a one-line presence summary so the output stays readable."
    ),
)
def session_show_cmd(
    session_id: str, project_dir: Path, output_format: str, full: bool
) -> None:
    """Print one session's YAML (text) or structured data (json).

    In `text` format, appends a brief review-artifact summary noting
    whether ``self-review.md`` and ``pm-response.yaml`` are committed
    to the session directory. ``--full`` expands them inline.
    """
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    try:
        session = load_session(resolved, session_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc

    if output_format == "json":
        click.echo(session.model_dump_json(indent=2, exclude_none=True))
        return

    from tripwire.core.session_store import session_yaml_path

    yaml_path = session_yaml_path(resolved, session_id)
    click.echo(yaml_path.read_text(encoding="utf-8"))

    # v0.7.10 §3.A2 — show the resolved (provider, model, effort) so a
    # human can confirm the route before launch.
    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.core.spawn_routing import UnknownTaskKindError, resolve_route

    spawn_defaults = load_resolved_spawn_config(resolved, session=session)
    task_kind = spawn_defaults.config.task_kind
    click.echo("Routing:")
    try:
        route = resolve_route(task_kind, resolved)
        click.echo(f"  task_kind: {route.task_kind}")
        click.echo(f"  provider: {route.provider}")
        click.echo(f"  model: {route.model}")
        click.echo(f"  effort: {route.effort}")
    except UnknownTaskKindError as exc:
        click.echo(f"  task_kind: {task_kind!r} — UNKNOWN ({exc})")

    from tripwire.core import paths as _paths

    sdir = _paths.session_dir(resolved, session_id)
    sr_path = sdir / "self-review.md"
    pr_path = sdir / "pm-response.yaml"

    click.echo("Review artifacts:")
    for label, path in (("self-review.md", sr_path), ("pm-response.yaml", pr_path)):
        if path.is_file():
            click.echo(f"  {label}: present")
        else:
            click.echo(f"  {label}: missing")

    if full:
        for label, path in (
            ("self-review.md", sr_path),
            ("pm-response.yaml", pr_path),
        ):
            if not path.is_file():
                continue
            click.echo()
            click.echo(f"--- {label} ---")
            click.echo(path.read_text(encoding="utf-8"))
