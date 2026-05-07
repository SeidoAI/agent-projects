"""`tripwire migrate` — schema/layout migrations for existing projects.

Subcommands:

- ``tripwire migrate templates`` — move a pre-v0.10.0 flat-layout project
  into the consolidated ``templates/`` layout.
- ``tripwire migrate graph`` — relocate the derived graph cache from
  ``graph/`` into ``nodes/``.
- ``tripwire migrate graph-edges`` — rewrite pre-v0.9 edge type strings
  in the cache (``references`` → ``refs``, ``blocked_by`` → ``depends_on``,
  ``related`` → ``refs``).

All three are idempotent — running twice is a no-op.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import click
import yaml

from tripwire.core import paths

# Source (flat) → destination (under templates/) mapping for the v0.10.0
# layout migration. The destination paths are now the canonical layout
# (defined as constants on ``core/paths.py``); the legacy source names
# are inlined here because this command is the only consumer.
_TEMPLATE_RENAMES: tuple[tuple[str, str], ...] = (
    ("agents", paths.AGENTS_DIR),                       # → templates/agents
    ("enums", paths.ENUMS_DIR),                          # → templates/enums
    ("issue_templates", paths.ISSUE_TEMPLATES_DIR),     # → templates/issues
    ("session_templates", paths.SESSION_TEMPLATES_DIR), # → templates/sessions
    ("comment_templates", paths.COMMENT_TEMPLATES_DIR), # → templates/comments
    ("orchestration", paths.ORCHESTRATION_DIR),         # → templates/orchestration
)


@click.group(name="migrate")
def migrate_cmd() -> None:
    """Run a one-shot schema/layout migration on the project at cwd."""


@migrate_cmd.command("templates")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to migrate.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the moves without performing them.",
)
def migrate_templates_cmd(project_dir: Path, dry_run: bool) -> None:
    """Migrate a pre-v0.10.0 project to the consolidated templates/ layout.

    Moves these flat-layout directories into ``templates/``:

      \b
      agents/             → templates/agents/
      enums/              → templates/enums/
      issue_templates/    → templates/issues/
      session_templates/  → templates/sessions/
      comment_templates/  → templates/comments/
      orchestration/      → templates/orchestration/

    Uses ``git mv`` when the project is a git repo (preserves history);
    falls back to ``shutil.move`` otherwise. Idempotent — directories
    that don't exist (already migrated) are skipped silently.
    """
    project_dir = project_dir.expanduser().resolve()
    if not (project_dir / "project.yaml").is_file():
        raise click.ClickException(
            f"{project_dir} doesn't look like a tripwire project "
            "(no project.yaml at the root)."
        )

    is_git_repo = (project_dir / ".git").exists()

    moved: list[tuple[str, str]] = []
    skipped: list[str] = []

    for src_rel, dest_rel in _TEMPLATE_RENAMES:
        src = project_dir / src_rel
        dest = project_dir / dest_rel

        if not src.exists():
            skipped.append(f"{src_rel} (not present — already migrated or never created)")
            continue

        if dest.exists():
            raise click.ClickException(
                f"Cannot migrate {src_rel}/ → {dest_rel}/ — destination "
                f"already exists. Manual cleanup required: inspect "
                f"{dest} and merge or remove before retrying."
            )

        # Ensure parent (templates/) exists.
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            click.echo(f"[dry-run] would move: {src_rel}/ → {dest_rel}/")
            moved.append((src_rel, dest_rel))
            continue

        if is_git_repo:
            try:
                subprocess.run(
                    ["git", "mv", str(src), str(dest)],
                    cwd=project_dir,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                raise click.ClickException(
                    f"git mv {src_rel} {dest_rel} failed: "
                    f"{exc.stderr.decode('utf-8', errors='replace').strip()}"
                ) from exc
        else:
            shutil.move(str(src), str(dest))

        moved.append((src_rel, dest_rel))
        click.echo(f"moved {src_rel}/ → {dest_rel}/")

    # Summary
    if not moved and not skipped:
        click.echo("Nothing to migrate.")
        return

    if dry_run:
        click.echo(f"\n{len(moved)} dir(s) would be moved (dry run — no changes).")
        return

    if moved:
        click.echo(f"\nMigrated {len(moved)} dir(s).")
        if is_git_repo:
            click.echo(
                "Review with `git status` and commit when satisfied. "
                "Run `tripwire validate` to confirm the project loads."
            )
        else:
            click.echo("Run `tripwire validate` to confirm the project loads.")
    if skipped:
        click.echo(f"\nSkipped {len(skipped)} dir(s):")
        for s in skipped:
            click.echo(f"  - {s}")


# ---------------------------------------------------------------------------
# graph migration — collapses ``graph/`` into ``nodes/``
# ---------------------------------------------------------------------------

# (legacy → canonical) for the v0.10.0 graph relocation. The cache moves
# alongside the source nodes; the lock follows it.
_GRAPH_RENAMES: tuple[tuple[str, str], ...] = (
    ("graph/index.yaml", paths.GRAPH_CACHE),
    ("graph/.index.lock", paths.GRAPH_LOCK),
)


@migrate_cmd.command("graph")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to migrate.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the moves without performing them.",
)
def migrate_graph_cmd(project_dir: Path, dry_run: bool) -> None:
    """Migrate the derived graph cache from ``graph/`` to ``nodes/``.

    Moves:

      \b
      graph/index.yaml     → nodes/tripwire-graph-index.yaml
      graph/.index.lock    → nodes/.tripwire-graph-index.lock

    The cache lives alongside the source nodes since v0.10.0 — the
    standalone ``graph/`` directory was redundant. The new filename is
    namespaced (``tripwire-graph-index``) so it can't collide with a
    user-authored node id; the validator rejects that id.

    Uses ``git mv`` when the project is a git repo (preserves history);
    falls back to ``shutil.move`` otherwise. After the moves succeed, an
    empty ``graph/`` directory at the project root is removed. Idempotent.
    """
    project_dir = project_dir.expanduser().resolve()
    if not (project_dir / "project.yaml").is_file():
        raise click.ClickException(
            f"{project_dir} doesn't look like a tripwire project "
            "(no project.yaml at the root)."
        )

    is_git_repo = (project_dir / ".git").exists()

    moved: list[tuple[str, str]] = []
    skipped: list[str] = []

    for src_rel, dest_rel in _GRAPH_RENAMES:
        src = project_dir / src_rel
        dest = project_dir / dest_rel

        if not src.exists():
            skipped.append(f"{src_rel} (not present — already migrated or never created)")
            continue

        if dest.exists():
            raise click.ClickException(
                f"Cannot migrate {src_rel} → {dest_rel} — destination "
                f"already exists. Manual cleanup required: inspect "
                f"{dest} and merge or remove before retrying."
            )

        dest.parent.mkdir(parents=True, exist_ok=True)

        if dry_run:
            click.echo(f"[dry-run] would move: {src_rel} → {dest_rel}")
            moved.append((src_rel, dest_rel))
            continue

        if is_git_repo:
            try:
                subprocess.run(
                    ["git", "mv", str(src), str(dest)],
                    cwd=project_dir,
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:
                stderr = exc.stderr.decode("utf-8", errors="replace").strip()
                # Gitignored / untracked files (the runtime lock) can't
                # be `git mv`'d. Fall back to plain shutil.move — git
                # neither tracked the source nor needs to know about
                # the destination.
                if "not under version control" in stderr:
                    shutil.move(str(src), str(dest))
                else:
                    raise click.ClickException(
                        f"git mv {src_rel} {dest_rel} failed: {stderr}"
                    ) from exc
        else:
            shutil.move(str(src), str(dest))

        moved.append((src_rel, dest_rel))
        click.echo(f"moved {src_rel} → {dest_rel}")

    # Remove the now-empty `graph/` directory if anything was moved.
    if not dry_run and moved:
        graph_dir = project_dir / "graph"
        if graph_dir.is_dir() and not any(graph_dir.iterdir()):
            graph_dir.rmdir()
            click.echo("removed empty graph/ directory")

    if not moved and not skipped:
        click.echo("Nothing to migrate.")
        return
    if dry_run:
        click.echo(f"\n{len(moved)} file(s) would be moved (dry run — no changes).")
        return
    if moved:
        click.echo(f"\nMigrated {len(moved)} file(s).")
        if is_git_repo:
            click.echo(
                "Review with `git status` and commit when satisfied. "
                "Run `tripwire validate` to confirm the project loads."
            )
        else:
            click.echo("Run `tripwire validate` to confirm the project loads.")
    if skipped:
        click.echo(f"\nSkipped {len(skipped)} file(s):")
        for s in skipped:
            click.echo(f"  - {s}")


# ---------------------------------------------------------------------------
# graph-edges migration — rewrites pre-v0.9 edge type strings in the cache
# ---------------------------------------------------------------------------

# Pre-v0.9 → canonical (v0.9+) edge type rewrites. Only the keys present here
# are rewritten; everything else (already-canonical kinds, unknown future
# kinds) passes through untouched. ``parent`` was promoted to a canonical
# EdgeKind in the rip, so it's deliberately absent from the map.
_GRAPH_EDGE_RENAMES: dict[str, str] = {
    "references": "refs",
    "related": "refs",
    "blocked_by": "depends_on",
}


@migrate_cmd.command("graph-edges")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to migrate.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print the rewrites without performing them.",
)
def migrate_graph_edges_cmd(project_dir: Path, dry_run: bool) -> None:
    """Rewrite pre-v0.9 edge type strings in the graph cache.

    Pre-v0.9 caches stored edge kinds as ``references``, ``blocked_by``,
    and ``related``. v0.9+ uses the canonical taxonomy (``refs``,
    ``depends_on``). This command rewrites every legacy ``type:`` value
    in ``nodes/tripwire-graph-index.yaml`` in place.

    Run this once after upgrading. Idempotent — already-canonical caches
    are no-ops. Missing cache file is also a no-op (the cache will be
    rebuilt fresh the next time ``tripwire validate`` runs).
    """
    project_dir = project_dir.expanduser().resolve()
    if not (project_dir / "project.yaml").is_file():
        raise click.ClickException(
            f"{project_dir} doesn't look like a tripwire project "
            "(no project.yaml at the root)."
        )

    cache_path = project_dir / paths.GRAPH_CACHE
    if not cache_path.is_file():
        click.echo(
            f"No cache file at {paths.GRAPH_CACHE} — nothing to migrate. "
            "Run `tripwire validate` to build a fresh canonical cache."
        )
        return

    raw = cache_path.read_text(encoding="utf-8")
    data: Any = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise click.ClickException(
            f"{paths.GRAPH_CACHE} is not a YAML mapping; refusing to rewrite."
        )

    edges = data.get("edges") or []
    rewritten = 0
    already_canonical = 0
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        current = edge.get("type")
        if not isinstance(current, str):
            continue
        if current in _GRAPH_EDGE_RENAMES:
            edge["type"] = _GRAPH_EDGE_RENAMES[current]
            rewritten += 1
        else:
            already_canonical += 1

    if rewritten == 0:
        click.echo(
            f"All {already_canonical} edge(s) already canonical — nothing to do."
        )
        return

    if dry_run:
        click.echo(
            f"[dry-run] would rewrite {rewritten} edge(s) "
            f"({already_canonical} already canonical)."
        )
        return

    cache_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    click.echo(
        f"Rewrote {rewritten} edge(s) "
        f"({already_canonical} already canonical) in {paths.GRAPH_CACHE}."
    )


__all__ = ["migrate_cmd"]
