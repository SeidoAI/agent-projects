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
from tripwire.runtimes.base import PreppedSession

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
    resume: bool = False,
) -> list[WorktreeEntry]:
    """Create one git worktree per session.repos entry.

    The first entry in ``session.repos`` is the code worktree — it's
    where CLAUDE.md and .claude/skills/ get written and where the
    agent cds into. Additional worktrees (typically the
    project-tracking repo) are referenced from CLAUDE.md by their
    absolute paths.

    On ``resume=True``, existing worktrees and existing branches are
    reused — we assume a prior spawn set them up and the agent was
    paused or failed. On ``resume=False`` (default), existing worktree
    paths or branches raise RuntimeError.
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
            if not resume:
                raise RuntimeError(
                    f"Worktree path {wt_path} already exists. "
                    f"Use 'tripwire session cleanup {session.id}' "
                    f"or re-spawn with --resume."
                )
            # resume: reuse existing worktree
        else:
            if resume:
                raise RuntimeError(
                    f"Worktree {wt_path} was expected to exist for "
                    f"--resume but does not. Run "
                    f"'tripwire session cleanup {session.id}' then "
                    f"spawn without --resume."
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


def _skills_hash(skill_names: list[str]) -> str:
    """Stable fingerprint of the requested skill set."""
    import hashlib

    joined = "\n".join(sorted(skill_names))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def copy_skills(*, worktree: Path, skill_names: list[str]) -> None:
    """Copy each named skill from tripwire.templates.skills into
    <worktree>/.claude/skills/<name>/.

    Idempotent: compares the requested skill set against the sentinel
    at <worktree>/.claude/.tripwire-skills-hash. If the set matches
    and every skill file is present, this is a no-op. Otherwise the
    existing .claude/skills/ is backed up and re-populated from
    scratch. Always appends .claude/ and .tripwire/ to the worktree's
    info/exclude.
    """
    source_root = files("tripwire.templates.skills")

    if skill_names:
        for name in skill_names:
            skill_src = source_root / name / "SKILL.md"
            if not skill_src.is_file():
                raise RuntimeError(
                    f"Skill '{name}' not found in tripwire.templates.skills. "
                    f"Check agents/<id>.yaml.context.skills."
                )

        dest_root = worktree / ".claude" / "skills"
        sentinel = worktree / ".claude" / ".tripwire-skills-hash"
        wanted = _skills_hash(skill_names)

        current = sentinel.read_text().strip() if sentinel.is_file() else ""
        all_present = all(
            (dest_root / n / "SKILL.md").is_file() for n in skill_names
        )

        if current != wanted or not all_present:
            if dest_root.exists():
                ts = datetime.now(tz=timezone.utc).strftime(
                    "%Y%m%dT%H%M%S%f"
                )
                backup = worktree / ".claude" / f"skills.bak.{ts}"
                # Walk children and move to avoid "Directory not empty"
                # from os.rename on non-empty dest dirs.
                import shutil as _sh

                _sh.move(str(dest_root), str(backup))

            dest_root.mkdir(parents=True, exist_ok=True)
            for name in skill_names:
                src_dir = source_root / name
                dst_dir = dest_root / name
                _copy_traversable(src_dir, dst_dir)

            sentinel.parent.mkdir(parents=True, exist_ok=True)
            sentinel.write_text(wanted + "\n", encoding="utf-8")

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


def _resolve_gitdir(worktree: Path) -> Path:
    """Return the directory where per-worktree git metadata lives.

    For a normal checkout this is ``<worktree>/.git``. For a ``git
    worktree``-created worktree the ``.git`` entry is a file pointing
    at ``<main-repo>/.git/worktrees/<name>``; we resolve it via
    ``git rev-parse --git-dir``.
    """
    import subprocess

    plain_gitdir = worktree / ".git"
    if plain_gitdir.is_dir():
        return plain_gitdir
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(worktree),
            capture_output=True,
            text=True,
            check=True,
        )
        gitdir = Path(r.stdout.strip())
        if not gitdir.is_absolute():
            gitdir = (worktree / gitdir).resolve()
        return gitdir
    except (subprocess.SubprocessError, FileNotFoundError):
        return plain_gitdir


def _append_to_git_info_exclude(worktree: Path) -> None:
    """Append .claude/ and .tripwire/ to the worktree's local gitignore
    (info/exclude). Idempotent — existing entries are detected by line
    match. For ``git worktree``-created worktrees this writes to
    ``<main-repo>/.git/worktrees/<name>/info/exclude``."""
    gitdir = _resolve_gitdir(worktree)
    exclude_path = gitdir / "info" / "exclude"
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


def _template_env():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    import tripwire

    templates_root = (
        Path(tripwire.__file__).parent / "templates" / "worktree"
    )
    return Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_claude_md(
    *,
    code_worktree: Path,
    agent_id: str,
    skill_names: list[str],
    worktrees: list[WorktreeEntry],
    session_id: str,
) -> None:
    """Render <code_worktree>/CLAUDE.md from the template. Back up any
    existing CLAUDE.md first."""
    target = code_worktree / "CLAUDE.md"
    if target.exists():
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = code_worktree / f"CLAUDE.md.bak.{ts}"
        target.rename(backup)

    env = _template_env()
    tpl = env.get_template("CLAUDE.md.j2")
    out = tpl.render(
        agent_id=agent_id,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session_id,
    )
    target.write_text(out, encoding="utf-8")


def render_kickoff(*, code_worktree: Path, prompt: str) -> None:
    """Write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md.

    This file is what the operator pastes (manual mode) and what the
    tmux send-keys step delivers on ready-probe timeout."""
    kickoff = code_worktree / ".tripwire" / "kickoff.md"
    kickoff.parent.mkdir(parents=True, exist_ok=True)
    kickoff.write_text(prompt, encoding="utf-8")


def _load_project_slug(project_dir: Path) -> str:
    from tripwire.core.store import load_project

    proj = load_project(project_dir)
    return proj.name.lower().replace(" ", "-")


def run(
    *,
    session: AgentSession,
    project_dir: Path,
    runtime,
    max_turns_override: int | None = None,
    claude_session_id: str | None = None,
    resume: bool = False,
) -> PreppedSession:
    """Orchestrate all prep steps:

      1. validate_environment on the selected runtime
      2. resolve worktrees (one per session.repos)
      3. copy skills into <code-worktree>/.claude/skills/
      4. render CLAUDE.md
      5. render prompt + kickoff.md

    Returns a PreppedSession the runtime's ``start`` consumes.
    """
    import uuid as _uuid

    import yaml as _yaml

    from tripwire.core.handoff_store import load_handoff
    from tripwire.core.paths import session_plan_path
    from tripwire.core.spawn_config import (
        load_resolved_spawn_config,
        render_prompt,
        render_system_append,
    )

    runtime.validate_environment()

    handoff = load_handoff(project_dir, session.id)
    if handoff is None:
        raise RuntimeError(f"handoff.yaml not found for session '{session.id}'")
    branch = handoff.branch

    from tripwire.core.branch_naming import parse_branch_name

    try:
        branch_type, _ = parse_branch_name(branch)
    except Exception:
        branch_type = "feat"

    worktrees = resolve_worktrees(
        session=session,
        project_dir=project_dir,
        branch=branch,
        base_ref="HEAD",
        resume=resume,
    )
    if not worktrees:
        raise RuntimeError(
            f"session '{session.id}' has no repos configured"
        )

    code_worktree = Path(worktrees[0].worktree_path)

    # Look up the agent's declared skills
    skill_names: list[str] = []
    agent_yaml = project_dir / "agents" / f"{session.agent}.yaml"
    if agent_yaml.is_file():
        try:
            agent_data = _yaml.safe_load(
                agent_yaml.read_text(encoding="utf-8")
            ) or {}
            context = agent_data.get("context") or {}
            skills = context.get("skills") or []
            if isinstance(skills, list):
                skill_names = [str(s) for s in skills]
        except Exception:
            skill_names = []

    copy_skills(worktree=code_worktree, skill_names=skill_names)

    render_claude_md(
        code_worktree=code_worktree,
        agent_id=session.agent,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session.id,
    )

    # Build the kickoff prompt
    plan_path = session_plan_path(project_dir, session.id)
    if not plan_path.is_file():
        raise RuntimeError(f"plan.md not found at {plan_path}")
    plan_content = plan_path.read_text(encoding="utf-8")

    resolved = load_resolved_spawn_config(project_dir, session=session)
    if max_turns_override is not None:
        resolved.config.max_turns = max_turns_override

    try:
        proj_slug = _load_project_slug(project_dir)
    except Exception:
        proj_slug = "unknown"

    prompt = render_prompt(
        resolved,
        plan=plan_content,
        agent=session.agent,
        session_id=session.id,
        session_name=session.name,
        branch_type=branch_type,
    )
    system_append = render_system_append(
        resolved,
        session_id=session.id,
        project_slug=proj_slug,
    )

    render_kickoff(code_worktree=code_worktree, prompt=prompt)

    csid = claude_session_id or str(_uuid.uuid4())

    return PreppedSession(
        session_id=session.id,
        session=session,
        project_dir=project_dir,
        code_worktree=code_worktree,
        worktrees=worktrees,
        claude_session_id=csid,
        prompt=prompt,
        system_append=system_append,
        spawn_defaults=resolved,
        resume=resume,
    )
