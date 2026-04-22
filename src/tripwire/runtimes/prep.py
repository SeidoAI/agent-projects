"""Runtime-agnostic prep pipeline.

Runs once per spawn before the runtime's ``start``:
- resolve_worktrees: create git worktrees for every session.repos entry
- copy_skills: copy the agent's declared skills into <code-worktree>/.claude/skills
- render_claude_md: render CLAUDE.md from the template
- render_kickoff: write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md
- run: the orchestrator that calls all of the above and returns PreppedSession
"""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from tripwire.core.git_helpers import (
    branch_exists,
    worktree_add,
    worktree_path_for_session,
)
from tripwire.models.session import AgentSession, WorktreeEntry

_MANAGED_EXCLUDES = (".claude/", ".tripwire/")


def _resolve_clone_path(project_dir: Path, repo: str) -> Path | None:
    """Look up the local clone path for a repo slug.

    Delegates to the implementation that already exists in
    ``cli/session.py`` so we keep a single source of truth for the
    project.yaml.repos lookup logic.
    """
    from tripwire.cli.session import _resolve_clone_path as _impl

    return _impl(project_dir, repo)


def resolve_worktrees(
    *,
    session: AgentSession,
    project_dir: Path,
    branch: str,
    base_ref: str,
) -> list[WorktreeEntry]:
    """Create one git worktree per session.repos entry.

    The first entry in ``session.repos`` is the code worktree — it's
    where CLAUDE.md and .claude/skills/ get written and where the
    agent cds into. Additional worktrees (typically the
    project-tracking repo) are referenced from CLAUDE.md by their
    absolute paths.

    Raises RuntimeError if any repo doesn't have a resolvable local
    clone or if the requested branch already exists in a clone.
    """
    entries: list[WorktreeEntry] = []
    for rb in session.repos:
        clone_path = _resolve_clone_path(project_dir, rb.repo)
        if clone_path is None:
            raise RuntimeError(
                f"No local clone for {rb.repo}. "
                f"Set local path in project.yaml repos."
            )
        wt_path = worktree_path_for_session(clone_path, session.id)
        if wt_path.exists():
            raise RuntimeError(
                f"Worktree path {wt_path} already exists. "
                f"Use 'tripwire session cleanup {session.id}' to remove it."
            )
        if branch_exists(clone_path, branch):
            raise RuntimeError(
                f"Branch '{branch}' already exists in {clone_path}. "
                f"Delete the branch or pick a different name."
            )
        worktree_add(clone_path, wt_path, branch, rb.base_branch or base_ref)
        entries.append(
            WorktreeEntry(
                repo=rb.repo,
                clone_path=str(clone_path),
                worktree_path=str(wt_path),
                branch=branch,
            )
        )
    return entries


def copy_skills(*, worktree: Path, skill_names: list[str]) -> None:
    """Copy each named skill from tripwire.templates.skills into
    <worktree>/.claude/skills/<name>/. Back up any pre-existing
    .claude/skills/ directory, then append .claude/ and .tripwire/ to
    the worktree's .git/info/exclude (idempotent).
    """
    source_root = files("tripwire.templates.skills")

    if skill_names:
        # Validate all skills exist before mutating anything.
        for name in skill_names:
            skill_src = source_root / name / "SKILL.md"
            if not skill_src.is_file():
                raise RuntimeError(
                    f"Skill '{name}' not found in tripwire.templates.skills. "
                    f"Check agents/<id>.yaml.context.skills."
                )

        dest_root = worktree / ".claude" / "skills"
        if dest_root.exists():
            ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
            backup = worktree / ".claude" / f"skills.bak.{ts}"
            dest_root.rename(backup)

        dest_root.mkdir(parents=True, exist_ok=True)
        for name in skill_names:
            src_dir = source_root / name
            dst_dir = dest_root / name
            _copy_traversable(src_dir, dst_dir)

    _append_to_git_info_exclude(worktree)


def _copy_traversable(src, dst: Path) -> None:
    """Recursively copy an importlib.resources Traversable into dst."""
    dst.mkdir(parents=True, exist_ok=True)
    for entry in src.iterdir():
        target = dst / entry.name
        if entry.is_dir():
            _copy_traversable(entry, target)
        else:
            target.write_bytes(entry.read_bytes())


def _append_to_git_info_exclude(worktree: Path) -> None:
    """Append .claude/ and .tripwire/ to the worktree's local gitignore
    (.git/info/exclude). Idempotent — existing entries are detected by
    line match."""
    exclude_path = worktree / ".git" / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    existing = (
        exclude_path.read_text(encoding="utf-8")
        if exclude_path.is_file()
        else ""
    )
    lines = existing.splitlines()
    additions: list[str] = []
    for entry in _MANAGED_EXCLUDES:
        if entry not in lines:
            additions.append(entry)
    if additions:
        needs_trailing_nl = existing and not existing.endswith("\n")
        with exclude_path.open("a", encoding="utf-8") as fh:
            if needs_trailing_nl:
                fh.write("\n")
            for entry in additions:
                fh.write(entry + "\n")
