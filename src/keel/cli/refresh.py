"""`keel refresh` — rebuild the graph cache from the filesystem.

Exposes `graph_cache.ensure_fresh` as a public command for debugging,
manual invocation, and agent workflows that want an explicit cache
rebuild without running the full validation gate.
"""

from __future__ import annotations

from pathlib import Path

import click

from keel.core.graph_cache import ensure_fresh


@click.command(name="refresh")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Path to the project root (contains project.yaml).",
)
@click.pass_context
def refresh_cmd(ctx: click.Context, project_dir: Path) -> None:
    """Rebuild the graph cache from the filesystem.

    This is a best-effort incremental rebuild — it compares file
    fingerprints in `graph/index.yaml` against what's on disk and only
    re-reads changed files. If the cache is up-to-date, this is a no-op.

    If you suspect the cache is wrong (e.g. after a hand-edit you didn't
    save through the CLI), delete `graph/index.yaml` and run
    `keel validate` — that forces a full rebuild from scratch.
    """
    resolved = project_dir.expanduser().resolve()
    rebuilt = ensure_fresh(resolved)
    if rebuilt:
        click.echo("graph cache rebuilt")
    else:
        click.echo("graph cache already up-to-date")
