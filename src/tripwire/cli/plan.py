"""`tripwire plan` — preview what init would produce without writing.

Dry-run of ``tripwire init``: shows the directory tree, file list,
sizes, and sources (jinja-rendered vs verbatim copy) that would be
created. Useful for understanding project structure before committing
to an init, or for the ``/pm-plan`` slash command to interpret.
"""

from __future__ import annotations

import json

import click

from tripwire.cli.init import _extract_key_prefix
from tripwire.core.planner import preview_init


@click.command(name="plan")
@click.option(
    "--name",
    default="my-project",
    show_default=True,
    help="Project name for the preview.",
)
@click.option(
    "--key-prefix",
    default=None,
    help="Key prefix (auto-derived from name if omitted).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format.",
)
def plan_cmd(name: str, key_prefix: str | None, output_format: str) -> None:
    """Preview what ``tripwire init`` would create.

    Shows directories, files, sizes, and sources without writing anything.
    """
    if key_prefix is None:
        # Use the same extraction as `tripwire init` so plan and init agree on
        # what prefix they would suggest (including camelCase handling).
        key_prefix = _extract_key_prefix(name) or "KP"

    preview = preview_init(
        project_name=name,
        key_prefix=key_prefix,
    )

    if output_format == "json":
        click.echo(json.dumps(preview.to_json(), indent=2))
    else:
        _render_text(preview)


def _render_text(preview: object) -> None:
    click.echo(f"Plan: {preview.target_name}")  # type: ignore[attr-defined]
    click.echo(f"  {preview.total_files} files, {len(preview.dirs)} directories")  # type: ignore[attr-defined]
    click.echo()
    click.echo("Directories:")
    for d in preview.dirs:  # type: ignore[attr-defined]
        click.echo(f"  {d}/")
    click.echo()
    click.echo("Files:")
    for f in preview.files:  # type: ignore[attr-defined]
        size = f"{f.size_bytes:,}B" if f.size_bytes else "empty"
        click.echo(f"  {f.rel_path}  ({size}, {f.source})")
