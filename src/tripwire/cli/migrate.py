"""`tripwire migrate` — schema/layout migrations for existing projects.

Subcommands:

- ``tripwire migrate templates`` — move a pre-v0.10.0 flat-layout project
  into the consolidated ``templates/`` layout.
- ``tripwire migrate graph`` — relocate the derived graph cache from
  ``graph/`` into ``nodes/``.
- ``tripwire migrate graph-edges`` — rewrite pre-v0.9 edge type strings
  in the cache (``references`` → ``refs``, ``blocked_by`` → ``depends_on``,
  ``related`` → ``refs``).
- ``tripwire migrate status-values`` — rewrite pre-v0.9.4 issue and
  session ``status:`` values to the canonical v0.9.4 taxonomy
  (``backlog`` → ``planned``, ``active`` → ``executing``, etc.).

All four are idempotent — running twice is a no-op.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import click
import yaml

from tripwire.core import paths
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)

# Source (flat) → destination (under templates/) mapping for the v0.10.0
# layout migration. The destination paths are now the canonical layout
# (defined as constants on ``core/paths.py``); the legacy source names
# are inlined here because this command is the only consumer.
_TEMPLATE_RENAMES: tuple[tuple[str, str], ...] = (
    ("agents", paths.AGENTS_DIR),  # → templates/agents
    ("enums", paths.ENUMS_DIR),  # → templates/enums
    ("issue_templates", paths.ISSUE_TEMPLATES_DIR),  # → templates/issues
    ("session_templates", paths.SESSION_TEMPLATES_DIR),  # → templates/sessions
    ("comment_templates", paths.COMMENT_TEMPLATES_DIR),  # → templates/comments
    ("orchestration", paths.ORCHESTRATION_DIR),  # → templates/orchestration
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
            skipped.append(
                f"{src_rel} (not present — already migrated or never created)"
            )
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
            skipped.append(
                f"{src_rel} (not present — already migrated or never created)"
            )
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


# ---------------------------------------------------------------------------
# status-values migration — rewrites pre-v0.9.4 issue + session statuses
# ---------------------------------------------------------------------------

# Pre-v0.9.4 → canonical status rewrites. The IssueStatus / SessionStatus
# StrEnums and their `_missing_` aliases were ripped in commit bb7b2ff;
# this command is the only path back to a loadable project for any tree
# that still carries the legacy values.
_ISSUE_STATUS_RENAMES: dict[str, str] = {
    "backlog": "planned",
    "todo": "queued",
    "in_progress": "executing",
    "done": "completed",
    "canceled": "abandoned",
}

_SESSION_STATUS_RENAMES: dict[str, str] = {
    "active": "executing",
    "waiting_for_ci": "executing",
    "waiting_for_review": "in_review",
    "waiting_for_deploy": "executing",
    "re_engaged": "executing",
}


def _rewrite_status_in_place(
    path: Path,
    rename_map: dict[str, str],
    *,
    dry_run: bool,
) -> tuple[bool, str | None, str | None]:
    """Rewrite ``status:`` in *path*'s frontmatter using *rename_map*.

    Returns ``(changed, before, after)``:
    - ``changed`` — whether the file's status was a legacy value that
      this call rewrote (or would rewrite, in dry-run).
    - ``before`` / ``after`` — the legacy and canonical strings, for
      output. ``None`` for files that needed no rewrite.

    Files that can't be parsed are skipped silently with ``(False, None,
    None)`` — the validator should already be flagging them, and this
    command's job is rewriting, not reporting.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False, None, None
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError:
        return False, None, None
    status = frontmatter.get("status")
    if not isinstance(status, str) or status not in rename_map:
        return False, None, None

    canonical = rename_map[status]
    if dry_run:
        return True, status, canonical

    frontmatter["status"] = canonical
    path.write_text(serialize_frontmatter_body(frontmatter, body), encoding="utf-8")
    return True, status, canonical


@migrate_cmd.command("status-values")
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
def migrate_status_values_cmd(project_dir: Path, dry_run: bool) -> None:
    """Rewrite pre-v0.9.4 ``status:`` values to the canonical taxonomy.

    Walks every ``issues/<KEY>/issue.yaml`` and
    ``sessions/<id>/session.yaml`` under the project, finds frontmatter
    ``status:`` values that match the legacy taxonomy, and rewrites
    them in place:

      \b
      Issue:    backlog → planned, todo → queued, in_progress → executing,
                done → completed, canceled → abandoned
      Session:  active / waiting_for_ci / waiting_for_deploy / re_engaged → executing,
                waiting_for_review → in_review

    Idempotent — files already on the canonical taxonomy are left alone.
    Missing files (no ``issues/``, no ``sessions/``) are tolerated.
    """
    project_dir = project_dir.expanduser().resolve()
    if not (project_dir / "project.yaml").is_file():
        raise click.ClickException(
            f"{project_dir} doesn't look like a tripwire project "
            "(no project.yaml at the root)."
        )

    rewritten: list[tuple[str, str, str]] = []  # (rel_path, before, after)
    scanned = 0

    # Issues — issues/<KEY>/issue.yaml
    issues_root = paths.issues_dir(project_dir)
    if issues_root.is_dir():
        for idir in sorted(p for p in issues_root.iterdir() if p.is_dir()):
            if idir.name.startswith("."):
                continue
            yaml_path = idir / paths.ISSUE_FILENAME
            if not yaml_path.is_file():
                continue
            scanned += 1
            changed, before, after = _rewrite_status_in_place(
                yaml_path, _ISSUE_STATUS_RENAMES, dry_run=dry_run
            )
            if changed and before is not None and after is not None:
                rewritten.append(
                    (str(yaml_path.relative_to(project_dir)), before, after)
                )

    # Sessions — sessions/<id>/session.yaml
    sessions_root = paths.sessions_dir(project_dir)
    if sessions_root.is_dir():
        for sdir in sorted(p for p in sessions_root.iterdir() if p.is_dir()):
            if sdir.name.startswith("."):
                continue
            yaml_path = sdir / paths.SESSION_FILENAME
            if not yaml_path.is_file():
                continue
            scanned += 1
            changed, before, after = _rewrite_status_in_place(
                yaml_path, _SESSION_STATUS_RENAMES, dry_run=dry_run
            )
            if changed and before is not None and after is not None:
                rewritten.append(
                    (str(yaml_path.relative_to(project_dir)), before, after)
                )

    if not rewritten:
        click.echo(
            f"All {scanned} file(s) already on canonical statuses — nothing to migrate."
        )
        return

    prefix = "[dry-run] would rewrite" if dry_run else "rewrote"
    for rel, before, after in rewritten:
        click.echo(f"{prefix}: {rel}  status: {before} → {after}")

    summary_verb = "would be rewritten" if dry_run else "rewritten"
    click.echo(
        f"\n{len(rewritten)} file(s) {summary_verb} "
        f"({scanned - len(rewritten)} already canonical)."
    )


__all__ = ["migrate_cmd"]
