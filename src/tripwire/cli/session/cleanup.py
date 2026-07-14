"""``tripwire session cleanup`` — remove worktrees for completed/abandoned sessions."""

from __future__ import annotations

from pathlib import Path

import click

from tripwire.cli._utils import require_project as _require_project
from tripwire.cli.session._group import session_cmd
from tripwire.core.git_helpers import (
    worktree_is_dirty,
    worktree_prune,
    worktree_remove,
)
from tripwire.core.session_store import list_sessions, save_session


@session_cmd.command("cleanup")
@click.argument("session_id", required=False, default=None)
@click.option(
    "--project-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=".",
    show_default=True,
)
@click.option(
    "--all",
    "clean_all",
    is_flag=True,
    default=False,
    help="Clean ALL session worktrees",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Skip dirty-worktree check",
)
@click.option(
    "--with-logs",
    "with_logs",
    is_flag=True,
    default=False,
    help="Also remove the session's log files from ~/.tripwire/logs/",
)
@click.option(
    "--preserve-work",
    "preserve_work",
    is_flag=True,
    default=False,
    help=(
        "Kill runtime processes and clear session locks, but KEEP "
        "worktrees, plan.md, and artifacts/ on disk. Use when you "
        "want to free up a stuck runtime without losing in-progress "
        "work. Default: full cleanup (worktrees + locks)."
    ),
)
def session_cleanup_cmd(
    session_id: str | None,
    project_dir: Path,
    clean_all: bool,
    force: bool,
    with_logs: bool,
    preserve_work: bool,
) -> None:
    """Remove worktrees for completed/abandoned sessions."""
    resolved = project_dir.expanduser().resolve()
    _require_project(resolved)

    sessions = list_sessions(resolved)
    clones_to_prune: set[str] = set()

    if session_id:
        targets = [s for s in sessions if s.id == session_id]
        if not targets:
            raise click.ClickException(f"session '{session_id}' not found")
    elif clean_all:
        if not click.confirm("Remove ALL session worktrees?"):
            return
        targets = sessions
    else:
        targets = [s for s in sessions if s.status in ("completed", "abandoned")]

    from tripwire.core.spawn_config import load_resolved_spawn_config
    from tripwire.runtimes import get_runtime

    cleaned = 0
    for session in targets:
        # If the runtime still has a live process (claude subprocess, etc.),
        # tear it down before ripping the worktree out from under it.
        try:
            spawn = load_resolved_spawn_config(resolved, session=session)
            runtime = get_runtime(spawn.invocation.runtime)
            if runtime.status(session) == "running":
                runtime.abandon(session)
        except (ValueError, RuntimeError, FileNotFoundError):
            # Best-effort — unknown runtime / missing config shouldn't
            # block worktree cleanup.
            pass

        # --preserve-work: skip the worktree teardown + log-rm passes
        # below. Locks for this session still get cleared (the spawn
        # process is dead, so the lock is stale by definition).
        if preserve_work:
            locks_dir = resolved / ".tripwire" / "locks"
            removed_locks = 0
            if locks_dir.is_dir():
                # Match locks belonging to this session — both the
                # exact-id form ``<sid>.lock`` and the ``*-<sid>.lock``
                # form some workflow gates use.
                for lock in locks_dir.glob("*.lock"):
                    name = lock.stem
                    if name == session.id or name.endswith(f"-{session.id}"):
                        try:
                            lock.unlink()
                            removed_locks += 1
                        except OSError:
                            pass
            click.echo(
                f"  Preserved work for '{session.id}' "
                f"(runtime killed; {removed_locks} lock(s) cleared; "
                "worktrees + plan.md kept)"
            )
            continue

        for wt in session.runtime_state.worktrees:
            wt_path = Path(wt.worktree_path)
            if not wt_path.exists():
                continue
            if not force and worktree_is_dirty(wt_path):
                click.echo(f"  Skipping {wt_path} — uncommitted changes (use --force)")
                continue
            clone_path = Path(wt.clone_path)
            worktree_remove(clone_path, wt_path)
            clones_to_prune.add(str(clone_path))
            cleaned += 1

        # Clear removed worktrees from runtime_state
        if session.runtime_state.worktrees:
            remaining = [
                wt
                for wt in session.runtime_state.worktrees
                if Path(wt.worktree_path).exists()
            ]
            session.runtime_state.worktrees = remaining
            save_session(resolved, session)

        # Orphan-worktree scan: filesystem worktrees matching
        # `*-wt-<session-id>` that weren't in runtime_state. Happens
        # when a spawn is interrupted before runtime_state gets
        # written, or when artefacts leaked from a pre-I5 dry-run.
        # Scan roots: every registered code-repo clone, plus
        # project_dir itself (v0.7.4 project-tracking worktrees live
        # as siblings of project_dir, not under any registered repo).
        recorded_paths = {
            Path(w.worktree_path).resolve() for w in session.runtime_state.worktrees
        }
        try:
            from tripwire.core.store import load_project

            proj = load_project(resolved)
        except Exception:
            proj = None
        scan_roots: list[Path] = []
        if proj and proj.repos:
            for _slug, repo_cfg in proj.repos.items():
                if repo_cfg.local:
                    clone = Path(repo_cfg.local).expanduser()
                    if clone.exists():
                        scan_roots.append(clone)
        if resolved.exists():
            scan_roots.append(resolved)

        suffix = f"-wt-{session.id}"
        for clone in scan_roots:
            for sibling in clone.parent.iterdir():
                if not sibling.is_dir() or not sibling.name.endswith(suffix):
                    continue
                if sibling.resolve() in recorded_paths:
                    continue  # already handled above
                if not force and worktree_is_dirty(sibling):
                    click.echo(
                        f"  Skipping orphan {sibling} — "
                        "uncommitted changes (use --force)"
                    )
                    continue
                worktree_remove(clone, sibling)
                clones_to_prune.add(str(clone))
                cleaned += 1
                click.echo(f"  Removed orphan: {sibling}")

        # Optionally drop the session's log files. Log files are named
        # <session_id>-<timestamp>.log under a shared {project_slug}
        # directory, so we glob-match rather than rm -rf the parent
        # (which would nuke other sessions' logs in the same project).
        if with_logs and session.runtime_state.log_path:
            log_parent = Path(session.runtime_state.log_path).expanduser().parent
            if log_parent.is_dir():
                removed = 0
                for log_file in log_parent.glob(f"{session.id}-*.log"):
                    log_file.unlink()
                    removed += 1
                if removed:
                    click.echo(f"  Removed {removed} log file(s) for '{session.id}'")

    for clone_str in clones_to_prune:
        worktree_prune(Path(clone_str))

    click.echo(f"Cleaned {cleaned} worktree(s)")
