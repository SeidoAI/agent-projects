"""``tripwire session batch-spawn`` — spawn N sessions after prompt-cache priming."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd


@session_cmd.command("batch-spawn")
@click.argument("session_ids", nargs=-1, required=True)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--prime/--no-prime",
    "prime",
    default=True,
    show_default=True,
    help=(
        "Send a no-op claude call with shared system content before "
        "the first spawn so subsequent spawns hit the warm prompt cache."
    ),
)
def session_batch_spawn_cmd(
    session_ids: tuple[str, ...],
    project_dir: Path,
    prime: bool,
) -> None:
    """Spawn N sessions in quick succession after priming the prompt cache.

    The shared system content for priming defaults to the project's
    ``CLAUDE.md``. Batches of one skip priming — the no-op call is not
    free.
    """
    from tripwire.core import batch_spawn as bs

    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    report = bs.batch_spawn(
        resolved,
        list(session_ids),
        prime=prime,
        prime_runner=bs.default_prime_runner,
        spawn_runner=bs.default_spawn_runner,
    )
    if report.primed:
        click.echo("Cache primed: ✓")
    elif prime and len(session_ids) > 1:
        click.echo(
            "Cache priming was attempted but did not succeed; "
            "sessions will spawn without warm-cache benefit."
        )
    for sid in report.spawned:
        click.echo(f"Spawned: {sid}")
    for sid, reason in report.failed:
        click.echo(f"Failed:  {sid} ({reason})", err=True)
    if report.failed:
        raise click.exceptions.Exit(1)
