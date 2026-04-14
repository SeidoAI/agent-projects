"""`keel enums list|show` — explore the active enums.

Read-only view over whatever `core.enum_loader.load_enums` returns for
this project. If the project has its own `enums/*.yaml` files, those
win; otherwise the packaged defaults are shown.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from keel.cli._utils import require_project as _require_project
from keel.core.enum_loader import load_enums

console = Console()


@click.group(name="enums")
def enums_cmd() -> None:
    """Explore the active enums (project override + packaged defaults)."""


@enums_cmd.command("list")
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
def enums_list(project_dir: Path, output_format: str) -> None:
    """List every enum active in this project."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    registry = load_enums(resolved)

    if output_format == "json":
        payload = {
            name: {
                "source": loaded.source,
                "values": list(loaded.value_ids()),
            }
            for name, loaded in registry.enums.items()
        }
        click.echo(json.dumps(payload, indent=2))
        return

    if not registry.enums:
        console.print("[dim]no enums active[/dim]")
        return

    table = Table(title="Active enums", show_header=True)
    table.add_column("enum")
    table.add_column("source")
    table.add_column("values")
    for name in sorted(registry.enums.keys()):
        loaded = registry.enums[name]
        values = ", ".join(loaded.value_ids())
        table.add_row(name, loaded.source, values)
    console.print(table)


@enums_cmd.command("show")
@click.argument("name")
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
def enums_show(name: str, project_dir: Path, output_format: str) -> None:
    """Show the values of a specific enum by NAME (e.g. issue_status)."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)
    registry = load_enums(resolved)

    loaded = registry.get(name)
    if loaded is None:
        raise click.ClickException(
            f"No enum named {name!r}. "
            f"Available: {', '.join(sorted(registry.enums.keys()))}"
        )

    if output_format == "json":
        click.echo(
            json.dumps(
                {
                    "name": loaded.name,
                    "description": loaded.description,
                    "source": loaded.source,
                    "values": [
                        {"id": v.id, "label": v.label, "color": v.color}
                        for v in loaded.values
                    ],
                },
                indent=2,
            )
        )
        return

    table = Table(
        title=f"{loaded.name}  ({loaded.source})",
        show_header=True,
    )
    table.add_column("id")
    table.add_column("label")
    table.add_column("color")
    for v in loaded.values:
        table.add_row(v.id, v.label, v.color or "")
    console.print(table)


# ============================================================================
# Helpers
# ============================================================================
