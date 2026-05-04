"""`tripwire heuristic` — manage heuristic suppression markers.

Subcommands:

* ``list`` — show registered heuristics and current marker counts.
* ``reset`` — delete suppression markers (forces re-fire on next
  ``tripwire validate``).
* ``gc`` — remove markers for entities that no longer exist.

The marker layer is described in
``src/tripwire/_internal/heuristics/_acks.py``. The CLI is a thin shell
over those primitives so PMs/agents can clear suppressions when the
underlying calibration has shifted but the condition_hash happens not
to have moved.
"""

from __future__ import annotations

from pathlib import Path

import click

from tripwire._internal.heuristics import (
    gc_markers,
    heuristic_specs,
    known_heuristic_ids,
    reset_markers,
)
from tripwire._internal.heuristics._acks import ACK_DIR_REL


@click.group("heuristic")
def heuristic_cmd() -> None:
    """Manage heuristic suppression markers."""


@heuristic_cmd.command("list")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def heuristic_list_cmd(project_dir: Path) -> None:
    """List registered heuristics with marker counts."""
    resolved = project_dir.expanduser().resolve()
    ack_root = resolved / ACK_DIR_REL

    rows: list[tuple[str, str, int, str]] = []
    for spec in heuristic_specs():
        hd = ack_root / spec.id
        count = sum(1 for _ in hd.glob("*.json")) if hd.is_dir() else 0
        rows.append((spec.id, spec.entity, count, spec.label))

    if not rows:
        click.echo("No heuristics registered.")
        return

    width_id = max(len(r[0]) for r in rows)
    width_entity = max(len(r[1]) for r in rows)
    for hid, entity, count, label in rows:
        click.echo(
            f"{hid.ljust(width_id)}  {entity.ljust(width_entity)}  "
            f"acked={count:<3}  {label}"
        )


@heuristic_cmd.command("reset")
@click.argument("heuristic_id", required=False)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--entity",
    "entity_uuid",
    default=None,
    help="Restrict reset to a single entity uuid (issue/session/node).",
)
@click.option(
    "--all",
    "reset_all",
    is_flag=True,
    default=False,
    help="Reset markers for every heuristic. Required when no id is given.",
)
def heuristic_reset_cmd(
    heuristic_id: str | None,
    project_dir: Path,
    entity_uuid: str | None,
    reset_all: bool,
) -> None:
    """Delete suppression markers for one or all heuristics."""
    resolved = project_dir.expanduser().resolve()

    if heuristic_id is None and not reset_all:
        raise click.UsageError(
            "supply a heuristic id or pass --all to reset every heuristic"
        )

    if heuristic_id is not None and heuristic_id not in known_heuristic_ids():
        raise click.UsageError(
            f"unknown heuristic {heuristic_id!r}. "
            f"Run `tripwire heuristic list` to see registered ids."
        )

    removed = reset_markers(
        resolved, heuristic_id=heuristic_id, entity_uuid=entity_uuid
    )
    label = heuristic_id or "<all>"
    target = f" entity={entity_uuid}" if entity_uuid else ""
    click.echo(f"reset {label}{target}: removed {removed} marker(s)")


@heuristic_cmd.command("gc")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
def heuristic_gc_cmd(project_dir: Path) -> None:
    """Remove markers for entities that no longer exist on disk."""
    from tripwire.core.validator import load_context

    resolved = project_dir.expanduser().resolve()
    ctx = load_context(resolved)

    live: set[str] = set()
    for bucket in (ctx.issues, ctx.nodes, ctx.sessions):
        for entity in bucket:
            uuid_value = entity.raw_frontmatter.get("uuid")
            if isinstance(uuid_value, str) and uuid_value:
                live.add(uuid_value)

    removed = gc_markers(resolved, live)
    click.echo(f"gc: removed {removed} stale marker(s) ({len(live)} live entities)")
