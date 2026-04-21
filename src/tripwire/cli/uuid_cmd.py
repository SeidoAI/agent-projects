"""`tripwire uuid` — generate RFC 4122 UUID4 values.

Outputs real uuid4 values with tracking annotations so agents can
assign them to entities without hand-crafting fake UUIDs.
"""

from __future__ import annotations

import uuid as _uuid

import click


@click.command(name="uuid")
@click.option(
    "--count",
    default=1,
    show_default=True,
    help="Number of UUIDs to generate.",
)
def uuid_cmd(count: int) -> None:
    """Generate one or more RFC 4122 UUID4 values.

    Each UUID is printed with a tracking comment so you can assign
    them to entities in order.
    """
    for i in range(1, count + 1):
        if count > 1:
            click.echo(f"# Entity {i}")
        click.echo(str(_uuid.uuid4()))
