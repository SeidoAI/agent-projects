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
# (defined as constants on ``core/paths.py``); the pre-migration source
# names are inlined here because this command is the only consumer.
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

# (source → canonical) for the v0.10.0 graph relocation. The cache moves
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
    ``depends_on``). This command rewrites every pre-v0.9 ``type:`` value
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
# that still carries the pre-v0.9.4 values.
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
    - ``changed`` — whether the file's status was a pre-v0.9.4 value that
      this call rewrote (or would rewrite, in dry-run).
    - ``before`` / ``after`` — the pre-v0.9.4 and canonical strings, for
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
    ``status:`` values that match the pre-v0.9.4 taxonomy, and rewrites
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


# ---------------------------------------------------------------------------
# storage migration — move pre-v0.13.1 flat entity dirs under `instances/`
# ---------------------------------------------------------------------------

# Source (flat) → destination (under `instances/`) mapping for the
# v0.13.1 layout cutover. Each entry is a top-level directory whose
# entire subtree relocates wholesale. The docs/issues/* directories
# merge into the corresponding `instances/issues/<KEY>/docs/` subtree.
_STORAGE_TOP_RENAMES: tuple[tuple[str, str], ...] = (
    ("sessions", paths.SESSIONS_DIR),  # → instances/sessions
    ("issues", paths.ISSUES_DIR),  # → instances/issues
    ("nodes", paths.NODES_DIR),  # → instances/nodes
)


def _git_mv_or_copy(
    src: Path,
    dest: Path,
    project_dir: Path,
    is_git_repo: bool,
) -> None:
    """Move *src* to *dest*, preferring `git mv` when *src* is tracked.

    Falls back to ``shutil.move`` either when the project isn't a git
    repo or when git reports "not under version control" for *src*
    (a gitignored runtime file like a lock).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_git_repo:
        try:
            subprocess.run(
                ["git", "mv", str(src), str(dest)],
                cwd=project_dir,
                check=True,
                capture_output=True,
            )
            return
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip()
            if "not under version control" not in stderr:
                raise click.ClickException(
                    f"git mv {src} → {dest} failed: {stderr}"
                ) from exc
    shutil.move(str(src), str(dest))


def _migrate_issue_docs(
    project_dir: Path,
    is_git_repo: bool,
    moved: list[tuple[str, str]],
) -> None:
    """Relocate ``docs/issues/<KEY>/*`` → ``instances/issues/<KEY>/docs/*``.

    Pre-v0.13.1 PM agents wrote developer.md / verified.md / comments/
    under ``docs/issues/<KEY>/`` (per the CLAUDE.md convention). Those
    files now live under ``instances/issues/<KEY>/docs/`` alongside the
    canonical issue.yaml.

    For each ``docs/issues/<KEY>/*`` source entry, move the entry into
    the issue's ``docs/`` subdir. Existing files at the destination are
    left alone (the caller has already gated this with --yes if any
    overlap was detected).
    """
    legacy_docs_issues = project_dir / "docs" / "issues"
    if not legacy_docs_issues.is_dir():
        return
    for issue_dir in sorted(p for p in legacy_docs_issues.iterdir() if p.is_dir()):
        key = issue_dir.name
        dest_docs = paths.issue_docs_dir(project_dir, key)
        dest_docs.mkdir(parents=True, exist_ok=True)
        for entry in sorted(issue_dir.iterdir()):
            dest = dest_docs / entry.name
            if dest.exists():
                # The bulk-move already promoted developer.md / verified.md
                # under instances/issues/<key>/. Merge silently — caller
                # opted in via --yes when destination conflicts existed.
                continue
            src_rel = str(entry.relative_to(project_dir))
            dest_rel = str(dest.relative_to(project_dir))
            _git_mv_or_copy(entry, dest, project_dir, is_git_repo)
            moved.append((src_rel, dest_rel))
        # Remove the now-empty issue dir.
        try:
            issue_dir.rmdir()
        except OSError:
            pass
    try:
        legacy_docs_issues.rmdir()
    except OSError:
        pass


def _migrate_lock_acks(
    project_dir: Path,
    is_git_repo: bool,
    moved: list[tuple[str, str]],
) -> None:
    """Rename transition lockfiles + ack markers to the v0.13.1 scheme.

    Pre-v0.13.1: ``.tripwire/locks/transition-<sid>.lock`` and
    ``.tripwire/acks/<prompt>-<sid>.json``. Post: lock gets a workflow
    segment (always ``coding-session`` for migrating projects, the
    only firing workflow today); ack swaps the order to put workflow
    first. Both directories live entirely under ``.tripwire/`` which
    is gitignored, so plain ``shutil.move`` is appropriate — git
    needn't track these renames.
    """
    # Transition locks
    locks_dir = project_dir / paths.LOCKS_SUBDIR
    if locks_dir.is_dir():
        for lock in sorted(locks_dir.iterdir()):
            if not lock.is_file():
                continue
            name = lock.name
            if not (name.startswith("transition-") and name.endswith(".lock")):
                continue
            # Already namespaced (transition-<workflow>-<sid>.lock):
            # leave it. Heuristic: the new name contains two hyphens
            # in addition to the transition prefix because workflow
            # ids contain a hyphen (e.g. coding-session).
            stripped = name[len("transition-") : -len(".lock")]
            if stripped.startswith("coding-session-"):
                continue
            sid = stripped
            new_name = f"transition-coding-session-{sid}.lock"
            dest = locks_dir / new_name
            if dest.exists():
                continue
            src_rel = str(lock.relative_to(project_dir))
            dest_rel = str(dest.relative_to(project_dir))
            shutil.move(str(lock), str(dest))
            moved.append((src_rel, dest_rel))

    # Ack markers
    acks_dir = project_dir / paths.ACKS_SUBDIR
    if acks_dir.is_dir():
        for marker in sorted(acks_dir.iterdir()):
            if not marker.is_file():
                continue
            name = marker.name
            if not name.endswith(".json"):
                continue
            stem = name[: -len(".json")]
            # Skip already-migrated markers — they begin with the
            # workflow id. The only firing workflow today is
            # coding-session.
            if stem.startswith("coding-session-"):
                continue
            # Pre-v0.13.1 name shape: ``<prompt>-<sid>.json``. We don't
            # know where prompt ends and sid begins from the filename
            # alone (both may contain hyphens). The pre-cutover
            # convention is `<prompt>-<sid>` where both segments are
            # opaque strings. We migrate by lifting the entire stem
            # into the new shape ``coding-session-<stem>.json`` — the
            # readers do exact filename match so the migration is
            # only required to be consistent, not parseable.
            #
            # A better cutover would require an external list of sids
            # to disambiguate; in practice every prompt id is shorter
            # than every session id, and the readers don't slice the
            # name, so the lift-by-prefix is sufficient.
            new_name = f"coding-session-{stem}.json"
            dest = acks_dir / new_name
            if dest.exists():
                continue
            src_rel = str(marker.relative_to(project_dir))
            dest_rel = str(dest.relative_to(project_dir))
            shutil.move(str(marker), str(dest))
            moved.append((src_rel, dest_rel))


@migrate_cmd.command("storage")
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
    help="Project root to migrate.",
)
@click.option(
    "--yes",
    is_flag=True,
    help=(
        "Confirm destructive merges. Required when any "
        "instances/<type>/ already contains files (pre-existing partial "
        "migration). Without --yes the command refuses to overwrite."
    ),
)
@click.option(
    "--skip-validate",
    is_flag=True,
    help=(
        "Skip the post-move ``tripwire validate --strict`` step. Useful "
        "when migrating a project whose entity content predates the "
        "current validator catalog (test fixtures, archived projects)."
    ),
)
def migrate_storage_cmd(project_dir: Path, yes: bool, skip_validate: bool) -> None:
    """Move a pre-v0.13.1 project to the consolidated `instances/` layout.

    Relocates the entity directories:

      \b
      sessions/            → instances/sessions/
      issues/              → instances/issues/
      nodes/               → instances/nodes/
      docs/issues/<KEY>/*  → instances/issues/<KEY>/docs/*

    And renames runtime markers under .tripwire/ to the v0.13.1 names:

      \b
      .tripwire/locks/transition-<sid>.lock
        → .tripwire/locks/transition-coding-session-<sid>.lock
      .tripwire/acks/<prompt>-<sid>.json
        → .tripwire/acks/coding-session-<sid>-<prompt>.json

    Uses ``git mv`` when the project is a git repo (preserves history);
    falls back to ``shutil.move`` for untracked files (gitignored
    runtime locks / markers).

    After all moves, runs ``tripwire validate --strict`` in-process. If
    validation fails, prints findings and exits non-zero. Does NOT
    auto-roll-back — recommend ``git reset --hard`` to undo.

    Idempotent: a project already on the v0.13.1 layout exits 0 with
    "nothing to migrate".
    """
    project_dir = project_dir.expanduser().resolve()
    if not (project_dir / "project.yaml").is_file():
        raise click.ClickException(
            f"{project_dir} doesn't look like a tripwire project "
            "(no project.yaml at the root)."
        )

    is_git_repo = (project_dir / ".git").exists()

    # Detect pre-v0.13.1 layout via the presence of any top-level
    # entity dir. If none present, the project is already migrated
    # (or never had any entities) — exit 0.
    pre_layout_present = [
        src_rel
        for src_rel, _dest_rel in _STORAGE_TOP_RENAMES
        if (project_dir / src_rel).is_dir()
    ]
    has_legacy_docs_issues = (project_dir / "docs" / "issues").is_dir()
    if not pre_layout_present and not has_legacy_docs_issues:
        # Look for legacy lock/ack names too — those alone can warrant
        # a migration even on a project whose entity dirs are already
        # under `instances/`.
        locks_dir = project_dir / paths.LOCKS_SUBDIR
        acks_dir = project_dir / paths.ACKS_SUBDIR
        has_legacy_lock = locks_dir.is_dir() and any(
            p.name.startswith("transition-")
            and p.name.endswith(".lock")
            and not p.name[len("transition-") :].startswith("coding-session-")
            for p in locks_dir.iterdir()
            if p.is_file()
        )
        has_legacy_ack = acks_dir.is_dir() and any(
            p.name.endswith(".json") and not p.name.startswith("coding-session-")
            for p in acks_dir.iterdir()
            if p.is_file()
        )
        if not has_legacy_lock and not has_legacy_ack:
            click.echo(
                "Project already on v0.13.1 storage layout — nothing to migrate."
            )
            return

    # Refuse to clobber a partially-populated destination unless --yes.
    if not yes:
        for _src_rel, dest_rel in _STORAGE_TOP_RENAMES:
            dest = project_dir / dest_rel
            if dest.is_dir() and any(dest.iterdir()):
                raise click.ClickException(
                    f"{dest_rel}/ already contains entries — refusing to "
                    f"merge into a partially-migrated tree. Re-run with "
                    f"`--yes` to confirm, or move the destination aside "
                    f"and retry."
                )

    moved: list[tuple[str, str]] = []
    skipped: list[str] = []

    # 1. Bulk-move top-level entity dirs.
    for src_rel, dest_rel in _STORAGE_TOP_RENAMES:
        src = project_dir / src_rel
        dest = project_dir / dest_rel

        if not src.is_dir():
            skipped.append(
                f"{src_rel}/ (not present — already migrated or never created)"
            )
            continue

        # Ensure dest parent (`instances/`) exists.
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            # `--yes` already gated this branch; merge the source's
            # children into the destination one at a time.
            for child in sorted(src.iterdir()):
                target = dest / child.name
                if target.exists():
                    # Conflict — leave caller to resolve. Continue with
                    # the rest so partial progress is captured.
                    skipped.append(
                        f"{src_rel}/{child.name} (destination already exists)"
                    )
                    continue
                child_src_rel = str(child.relative_to(project_dir))
                child_dest_rel = str(target.relative_to(project_dir))
                _git_mv_or_copy(child, target, project_dir, is_git_repo)
                moved.append((child_src_rel, child_dest_rel))
            # Remove the now-empty source directory.
            try:
                src.rmdir()
            except OSError:
                # Non-empty (a conflict above); leave it for manual
                # cleanup.
                pass
        else:
            _git_mv_or_copy(src, dest, project_dir, is_git_repo)
            moved.append((src_rel, dest_rel))

    # 2. Relocate docs/issues/<KEY>/* → instances/issues/<KEY>/docs/*
    _migrate_issue_docs(project_dir, is_git_repo, moved)

    # 3. Rename transition lockfiles + ack markers to the v0.13.1 scheme.
    _migrate_lock_acks(project_dir, is_git_repo, moved)

    # 4. Summary.
    if not moved and not skipped:
        click.echo("Nothing to migrate.")
        return

    for src_rel, dest_rel in moved:
        click.echo(f"moved {src_rel} → {dest_rel}")
    if skipped:
        click.echo(f"\nSkipped {len(skipped)} entry(ies):")
        for s in skipped:
            click.echo(f"  - {s}")

    click.echo(f"\nMigrated {len(moved)} path(s).")
    if skip_validate:
        click.echo("Skipping `tripwire validate --strict` per `--skip-validate`.")
        return
    if is_git_repo:
        click.echo(
            "Review with `git status` and commit when satisfied. "
            "Running `tripwire validate --strict` now to confirm…"
        )
    else:
        click.echo("Running `tripwire validate --strict` now to confirm…")

    # 5. Run validate in-process. Failure leaves the user with the
    #    moved tree on disk; the recommended undo is `git reset --hard`.
    from tripwire.cli.transition import validate_project

    report = validate_project(project_dir, strict=True, fix=False)
    if report.errors:
        click.echo(
            f"\nValidation reported {len(report.errors)} error(s) after "
            f"migration. Inspect them, then either fix in place or run "
            f"`git reset --hard` to roll back."
        )
        for err in report.errors[:10]:
            click.echo(f"  - {err.code}: {err.message}")
        if len(report.errors) > 10:
            click.echo(f"  ... ({len(report.errors) - 10} more)")
        raise click.exceptions.Exit(1)

    click.echo("Validation clean. Migration complete.")


__all__ = ["migrate_cmd"]
