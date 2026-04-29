"""Runtime-agnostic prep pipeline.

Runs once per spawn before the runtime's ``start``:
- resolve_worktrees: create git worktrees for every session.repos entry
- copy_skills: copy the agent's declared skills into <code-worktree>/.claude/skills
- render_claude_md: render CLAUDE.md from the template
- render_kickoff: write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md
- run: the orchestrator that calls all of the above and returns PreppedSession
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

from tripwire.core.branch_naming import SESSION_ID_PREFIX
from tripwire.core.git_helpers import (
    branch_exists,
    worktree_add,
    worktree_path_for_session,
)
from tripwire.models.session import AgentSession, WorktreeEntry
from tripwire.runtimes.base import PreppedSession

log = logging.getLogger("tripwire.runtimes.prep")

_MANAGED_EXCLUDES = (".claude/", ".tripwire/")

# Bump when the Jinja template under templates/worktree/CLAUDE.md.j2
# changes shape (e.g. new variables, restructured sections). The hash
# check that gates CLAUDE.md re-render folds this in, so a template
# change forces every session's CLAUDE.md to re-render on next spawn.
_CLAUDE_MD_TEMPLATE_VERSION = "2"


def _resolve_clone_path(project_dir: Path, repo: str) -> Path | None:
    """Look up the local clone path for a repo slug.

    Delegates to the implementation that already exists in
    ``cli/session.py`` so we keep a single source of truth for the
    project.yaml.repos lookup logic.
    """
    from tripwire.cli.session import _resolve_clone_path as _impl

    return _impl(project_dir, repo)


def _check_gh_available() -> None:
    """Fail fast if ``gh`` isn't on PATH or isn't authenticated.

    Called at the top of :func:`run` before any worktree mutation so
    operators learn at spawn time — not eight minutes in at complete —
    that the GitHub CLI dependency is missing. The post-v0.7.5 spawn
    flow opens draft PRs here and flips them to ready at complete; both
    steps need ``gh``.
    """
    if shutil.which("gh") is None:
        raise RuntimeError(
            "`gh` (GitHub CLI) is not on PATH. Install gh "
            "(https://cli.github.com) so spawn can open draft PRs at "
            "session-start. The complete-time PR flow also needs gh, "
            "so failing fast here beats failing eight minutes in."
        )
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "`gh auth status` failed — gh is on PATH but not "
            "authenticated. Run `gh auth login` and re-spawn."
        )


def _open_draft_pr(
    *,
    worktree: Path,
    branch: str,
    base_branch: str,
    session_id: str,
) -> str | None:
    """Open a draft PR on ``branch`` against ``base_branch``.

    Sequence per :doc:`spec §2.A <2026-04-24-v075-handoff>`:

      1. Empty marker commit (``git commit --allow-empty``).
      2. ``git push -u origin <branch>``.
      3. ``gh pr create --draft``.

    Returns the PR URL on success. Returns ``None`` when the worktree
    has no git remote (graceful skip — logs a warning and proceeds; the
    legacy create-PR-at-complete path covers the spawn). Raises
    :class:`subprocess.CalledProcessError` if a remote is configured
    but commit/push/gh fails — spawn errors loud rather than silently
    leaving an orphan branch.
    """
    remote_check = subprocess.run(
        ["git", "-C", str(worktree), "remote"],
        capture_output=True,
        text=True,
        check=False,
    )
    if remote_check.returncode != 0 or not remote_check.stdout.strip():
        log.warning(
            "worktree %s has no git remote; skipping draft PR creation "
            "(falling back to legacy create-at-complete path)",
            worktree,
        )
        return None

    subprocess.run(
        [
            "git",
            "-C",
            str(worktree),
            "commit",
            "--allow-empty",
            "-m",
            f"session({session_id}): start",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(worktree), "push", "-u", "origin", branch],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--base",
            base_branch,
            "--head",
            branch,
            "--title",
            f"session({session_id}): start",
            "--body",
            (
                f"Draft PR for session `{session_id}`. Opened at session-"
                f"start; will be flipped to ready at "
                f"`tripwire session complete`."
            ),
        ],
        cwd=str(worktree),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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
    project_resolved = project_dir.expanduser().resolve()
    for rb in session.repos:
        clone_path = _resolve_clone_path(project_dir, rb.repo)
        if clone_path is None:
            raise RuntimeError(
                f"No local clone for {rb.repo}. Set local path in project.yaml repos."
            )
        # v0.7.9 §A6 #4: if this repo's clone path resolves to project_dir,
        # skip — `maybe_add_project_tracking_worktree` cuts a worktree
        # off project_dir unconditionally and a second create at the same
        # path would explode with "worktree path already exists". The
        # strict pre-spawn check `check/repos_overlap` blocks this
        # configuration upstream; this is the defence-in-depth so an
        # operator who manages to slip past the check (or a future caller
        # that bypasses the CLI) doesn't get the cryptic git error.
        try:
            clone_resolved = clone_path.expanduser().resolve()
        except OSError:
            clone_resolved = clone_path
        if clone_resolved == project_resolved:
            log.warning(
                "session %s: repo %s clone path overlaps project_dir (%s); "
                "skipping redundant code-side worktree (PT pass will create it)",
                session.id,
                rb.repo,
                project_resolved,
            )
            continue
        wt_path = worktree_path_for_session(clone_path, session.id)
        draft_pr_url: str | None = None
        if wt_path.exists():
            if not resume:
                raise RuntimeError(
                    f"Worktree path {wt_path} already exists. "
                    f"Use 'tripwire session cleanup {session.id}' "
                    f"or re-spawn with --resume."
                )
            # resume: reuse existing worktree (and any prior draft PR)
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
            base_branch = rb.base_branch or base_ref
            worktree_add(clone_path, wt_path, branch, base_branch)
            draft_pr_url = _open_draft_pr(
                worktree=wt_path,
                branch=branch,
                base_branch=base_branch,
                session_id=session.id,
            )
        entries.append(
            WorktreeEntry(
                repo=rb.repo,
                clone_path=str(clone_path),
                worktree_path=str(wt_path),
                branch=branch,
                draft_pr_url=draft_pr_url,
            )
        )
    return entries


def _resolve_project_default_branch(project_dir: Path) -> str:
    """Best-effort guess of the project-tracking repo's default branch.

    Tries in order: ``origin/HEAD`` symbolic-ref (set by ``git clone``),
    then ``main``, then ``master``. Falls back to ``HEAD`` so a fresh
    repo with neither ``main`` nor ``master`` still produces a branch
    off whatever is currently checked out. This keeps the project
    agnostic to default-branch convention while avoiding silently
    basing ``proj/<sid>`` on an arbitrary feature branch the operator
    happens to have checked out.
    """
    import subprocess

    r = subprocess.run(
        [
            "git",
            "-C",
            str(project_dir),
            "symbolic-ref",
            "--short",
            "refs/remotes/origin/HEAD",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode == 0:
        ref = r.stdout.strip()
        if ref.startswith("origin/"):
            return ref.removeprefix("origin/")
        if ref:
            return ref
    for candidate in ("main", "master"):
        verify = subprocess.run(
            ["git", "-C", str(project_dir), "rev-parse", "--verify", candidate],
            capture_output=True,
            text=True,
            check=False,
        )
        if verify.returncode == 0:
            return candidate
    return "HEAD"


def maybe_add_project_tracking_worktree(
    *,
    project_dir: Path,
    session: AgentSession,
    resume: bool = False,
) -> WorktreeEntry | None:
    """Cut a ``proj/<session-slug>`` worktree off ``project_dir`` when
    it's a git repo with at least one remote. Returns ``None`` (logged
    INFO) when there's no remote or no ``.git``.
    """
    if not (project_dir / ".git").exists():
        log.info(
            "project_dir %s is not a git repo; skipping project-tracking "
            "worktree for session %s",
            project_dir,
            session.id,
        )
        return None

    remote_check = subprocess.run(
        ["git", "-C", str(project_dir), "remote"],
        capture_output=True,
        text=True,
        check=False,
    )
    if remote_check.returncode != 0 or not remote_check.stdout.strip():
        log.info(
            "project_dir %s has no git remote; skipping project-tracking "
            "worktree for session %s",
            project_dir,
            session.id,
        )
        return None

    slug = session.id.removeprefix(SESSION_ID_PREFIX).lower()
    proj_branch = f"proj/{slug}"
    proj_wt_path = worktree_path_for_session(project_dir, session.id)
    draft_pr_url: str | None = None

    if proj_wt_path.exists():
        if not resume:
            raise RuntimeError(
                f"Project-tracking worktree {proj_wt_path} already exists. "
                f"Use 'tripwire session cleanup {session.id}' "
                f"or re-spawn with --resume."
            )
        # resume: reuse existing worktree (and any prior draft PR)
    else:
        if resume:
            raise RuntimeError(
                f"Project-tracking worktree {proj_wt_path} was expected "
                f"to exist for --resume but does not. Run "
                f"'tripwire session cleanup {session.id}' then "
                f"spawn without --resume."
            )
        if branch_exists(project_dir, proj_branch):
            raise RuntimeError(
                f"Branch '{proj_branch}' already exists in {project_dir}. "
                f"Delete the branch or pick a different session id."
            )
        base_ref = _resolve_project_default_branch(project_dir)
        worktree_add(project_dir, proj_wt_path, proj_branch, base_ref)
        draft_pr_url = _open_draft_pr(
            worktree=proj_wt_path,
            branch=proj_branch,
            base_branch=base_ref,
            session_id=session.id,
        )

    return WorktreeEntry(
        repo=project_dir.name,
        clone_path=str(project_dir),
        worktree_path=str(proj_wt_path),
        branch=proj_branch,
        draft_pr_url=draft_pr_url,
    )


def _skills_hash(skill_names: list[str]) -> str:
    """Stable fingerprint of the requested skill set."""
    import hashlib

    joined = "\n".join(sorted(skill_names))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def inline_skills_for_codex(skill_names: list[str]) -> str:
    """Concatenate named skills' SKILL.md content into a single block.

    Codex sessions don't have a ``.claude/skills`` discovery mechanism;
    the agent only sees what's in the prompt. This helper reads each
    declared skill from ``tripwire.templates.skills.<name>/SKILL.md``
    and returns a markdown block prefixed with ``## Skills`` so the
    prep step can prepend it to the rendered ``{plan}`` prompt.

    Empty input → empty string (no header). Unknown skill names are
    silently dropped — copy_skills is the source of truth for skill
    existence and would have raised earlier in the prep pipeline; we
    don't double-validate here so re-prep cycles stay idempotent.
    """
    if not skill_names:
        return ""
    source_root = files("tripwire.templates.skills")
    chunks: list[str] = ["## Skills", ""]
    found_any = False
    for name in skill_names:
        skill_md = source_root / name / "SKILL.md"
        if not skill_md.is_file():
            continue
        found_any = True
        chunks.append(f"### {name}")
        chunks.append("")
        chunks.append(skill_md.read_text(encoding="utf-8"))
        chunks.append("")
    if not found_any:
        return ""
    return "\n".join(chunks)


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
        all_present = all((dest_root / n / "SKILL.md").is_file() for n in skill_names)

        if current != wanted or not all_present:
            if dest_root.exists():
                ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")
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
        exclude_path.read_text(encoding="utf-8") if exclude_path.is_file() else ""
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

    templates_root = Path(tripwire.__file__).parent / "templates" / "worktree"
    return Environment(
        loader=FileSystemLoader(str(templates_root)),
        autoescape=select_autoescape(disabled_extensions=("j2", "md")),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _claude_md_hash(
    *,
    agent_id: str,
    skill_names: list[str],
    worktrees: list[WorktreeEntry],
    session_id: str,
    concept_context: list | None = None,
) -> str:
    """Stable fingerprint of every input that feeds into CLAUDE.md.

    Folds in the template version so a Jinja-template change
    invalidates the sentinel too. Folds in the concept-context entries
    so a plan edit that adds/removes a [[ref]] re-renders CLAUDE.md.
    """
    import hashlib

    worktree_keys = [f"{w.repo}:{w.worktree_path}" for w in worktrees]
    concept_keys = [f"{c.id}:{c.exists}" for c in (concept_context or [])]
    joined = "\n".join(
        [
            f"template-version={_CLAUDE_MD_TEMPLATE_VERSION}",
            f"agent={agent_id}",
            f"session={session_id}",
            "skills=" + ",".join(sorted(skill_names)),
            "worktrees=" + ",".join(sorted(worktree_keys)),
            "concepts=" + ",".join(sorted(concept_keys)),
        ]
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def render_claude_md(
    *,
    code_worktree: Path,
    agent_id: str,
    skill_names: list[str],
    worktrees: list[WorktreeEntry],
    session_id: str,
    concept_context: list | None = None,
) -> None:
    """Render <code_worktree>/CLAUDE.md from the template.

    Idempotent via a sentinel file next to CLAUDE.md. If the sentinel
    matches the hash of the current inputs AND CLAUDE.md exists,
    returns without writing. Otherwise backs up any existing CLAUDE.md,
    rewrites from the template, and updates the sentinel. This keeps
    resume flows from accumulating a fresh CLAUDE.md.bak.<ts> on every
    spawn when nothing meaningful changed.

    `concept_context` is a list of `ConceptContextEntry` (from
    `tripwire.core.concept_context`). When non-empty, the template
    renders a "Concept context" section pointing the agent at the
    nodes referenced from plan.md.
    """
    target = code_worktree / "CLAUDE.md"
    sentinel = code_worktree / ".claude" / ".tripwire-claude-md-hash"
    wanted = _claude_md_hash(
        agent_id=agent_id,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session_id,
        concept_context=concept_context,
    )
    current = sentinel.read_text().strip() if sentinel.is_file() else ""

    if current == wanted and target.is_file():
        return

    if target.exists():
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        backup = code_worktree / f"CLAUDE.md.bak.{ts}"
        target.rename(backup)

    env = _template_env()
    tpl = env.get_template("CLAUDE.md.j2")
    out = tpl.render(
        agent_id=agent_id,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session_id,
        concept_context=concept_context or [],
    )
    target.write_text(out, encoding="utf-8")
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(wanted + "\n", encoding="utf-8")


def render_kickoff(*, code_worktree: Path, prompt: str) -> None:
    """Write the kickoff prompt to <code-worktree>/.tripwire/kickoff.md.

    This file is what the operator pastes (manual mode) and what
    the subprocess runtime's ``claude -p`` argv uses at start."""
    kickoff = code_worktree / ".tripwire" / "kickoff.md"
    kickoff.parent.mkdir(parents=True, exist_ok=True)
    kickoff.write_text(prompt, encoding="utf-8")


def install_claude_settings(*, worktree: Path) -> None:
    """Install ``<worktree>/.claude/settings.json`` with the
    ``validate-on-edit`` PostToolUse hook (KUI-110 Phase 1.4).

    Shares the template + merge helper with ``tripwire init`` and
    ``tripwire hooks install`` so all three install paths converge on
    the same shape. Failures are logged and swallowed — a settings
    install glitch must not block spawn.
    """
    from tripwire.cli.hooks import install_settings_into

    try:
        install_settings_into(worktree)
    except OSError as exc:
        log.warning(
            "claude settings install failed for %s: %s", worktree, exc
        )


def install_pre_push_hook(
    *, worktree: Path, project_dir: Path, session_id: str
) -> None:
    """Install the tripwire pre-push hook in this worktree (KUI-99).

    Reads ``project.yaml.tripwires.enabled``; on False, skips
    installation entirely. On True, renders
    ``templates/spawn/pre_push_hook.sh.j2`` into
    ``<worktree>/.git/hooks/pre-push`` and chmods it executable.

    The hook itself re-reads the project config on every push, so a
    late ``tripwires.enabled: false`` flip works without re-install.
    """
    from jinja2 import Environment, FileSystemLoader

    from tripwire.core.store import load_project

    project = load_project(project_dir)
    tripwires_cfg = getattr(project, "tripwires", None)
    if tripwires_cfg is not None and getattr(tripwires_cfg, "enabled", True) is False:
        log.info(
            "session %s: project.yaml.tripwires.enabled is False; skipping "
            "pre-push hook install",
            session_id,
        )
        return

    git_dir = worktree / ".git"
    if not git_dir.exists():
        log.info(
            "worktree %s has no .git; skipping pre-push hook install",
            worktree,
        )
        return

    # `.git` may be a file (linked worktrees) — resolve via `gitdir:`
    # pointer so the hook lands in the right hooks/ directory.
    if git_dir.is_file():
        text = git_dir.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith("gitdir:"):
                pointer = Path(line.removeprefix("gitdir:").strip())
                if not pointer.is_absolute():
                    pointer = (worktree / pointer).resolve()
                git_dir = pointer
                break

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    template_root = Path(__file__).resolve().parent.parent / "templates" / "spawn"
    env = Environment(
        loader=FileSystemLoader(str(template_root)), keep_trailing_newline=True
    )
    template = env.get_template("pre_push_hook.sh.j2")
    body = template.render(
        project_dir=str(project_dir.resolve()),
        session_id=session_id,
    )

    hook = hooks_dir / "pre-push"
    hook.write_text(body, encoding="utf-8")
    hook.chmod(0o755)


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
        render_resume_prompt,
        render_system_append,
    )

    runtime.validate_environment()

    # v0.7.5 — gh-availability is a hard prereq from spawn-start. Check
    # before the runtime touches the filesystem so a missing/unauthed
    # gh fails fast rather than eight minutes in at complete-time.
    _check_gh_available()

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

    # v0.7.4: cut a per-session project-tracking worktree so parallel
    # sessions don't race on sessions/<id>/ or issues/<KEY>/developer.md
    # writes. Only applies when project_dir is a git repo with a
    # remote — otherwise this is a no-op and the session writes into
    # the shared project_dir like pre-v0.7.4.
    proj_entry = maybe_add_project_tracking_worktree(
        project_dir=project_dir,
        session=session,
        resume=resume,
    )
    if proj_entry is not None:
        worktrees.append(proj_entry)

    # v0.7.9 §A6 #4: emptiness check moved here from after resolve_worktrees
    # so the PT-only case (every session.repo overlapped with project_dir
    # and was skipped) still resolves to one valid worktree.
    if not worktrees:
        raise RuntimeError(f"session '{session.id}' has no repos configured")

    code_worktree = Path(worktrees[0].worktree_path)

    # KUI-99: install the tripwire pre-push hook on every code worktree
    # so `git push` can't dodge `tripwire session complete`. Skipped
    # when project.yaml.tripwires.enabled is False (the helper handles
    # the check). Idempotent — overwrites any existing hook with the
    # current template.
    for wt in worktrees:
        try:
            install_pre_push_hook(
                worktree=Path(wt.worktree_path),
                project_dir=project_dir,
                session_id=session.id,
            )
        except (OSError, RuntimeError) as exc:
            log.warning(
                "session %s: pre-push hook install failed for %s: %s",
                session.id,
                wt.worktree_path,
                exc,
            )

    # KUI-110: plant `.claude/settings.json` in every worktree so the
    # PostToolUse `validate-on-edit` hook is in scope no matter which
    # worktree Claude Code resolves its settings against.
    for wt in worktrees:
        install_claude_settings(worktree=Path(wt.worktree_path))

    # Look up the agent's declared skills
    skill_names: list[str] = []
    agent_yaml = project_dir / "agents" / f"{session.agent}.yaml"
    if agent_yaml.is_file():
        try:
            agent_data = _yaml.safe_load(agent_yaml.read_text(encoding="utf-8")) or {}
            context = agent_data.get("context") or {}
            skills = context.get("skills") or []
            if isinstance(skills, list):
                skill_names = [str(s) for s in skills]
        except Exception:
            skill_names = []

    copy_skills(worktree=code_worktree, skill_names=skill_names)

    # Concept-context breadcrumbs: every [[ref]] in plan.md becomes a
    # row in CLAUDE.md so the agent reads the cited nodes at session
    # start (rather than discovering them mid-flight). Empty list if
    # plan.md is missing — render_claude_md treats that as "no
    # Concept context section".
    from tripwire.core.concept_context import extract_plan_concepts

    concept_context = extract_plan_concepts(project_dir, session.id)

    render_claude_md(
        code_worktree=code_worktree,
        agent_id=session.agent,
        skill_names=skill_names,
        worktrees=worktrees,
        session_id=session.id,
        concept_context=concept_context,
    )

    # Build the kickoff prompt. On resume we render the short
    # continuation template — claude already has the full conversation
    # history from its own jsonl; re-reading plan.md is the agent's
    # decision. On initial spawn we render the full template with
    # plan.md content inlined.
    plan_path = session_plan_path(project_dir, session.id)

    resolved = load_resolved_spawn_config(project_dir, session=session)
    if max_turns_override is not None:
        resolved.config.max_turns = max_turns_override

    try:
        proj_slug = _load_project_slug(project_dir)
    except Exception:
        proj_slug = "unknown"

    if resume:
        prompt = render_resume_prompt(
            resolved,
            session_id=session.id,
            plan_path=str(plan_path),
        )
    else:
        if not plan_path.is_file():
            raise RuntimeError(f"plan.md not found at {plan_path}")
        plan_content = plan_path.read_text(encoding="utf-8")
        prompt = render_prompt(
            resolved,
            plan=plan_content,
            agent=session.agent,
            session_id=session.id,
            session_name=session.name,
            branch_type=branch_type,
        )

    # KUI-94 skill-inlining: codex has no `.claude/skills/` discovery,
    # so the prompt is the only channel for skill content. Prepend a
    # `## Skills` block when the agent declares skills and the resolved
    # provider is codex.
    if resolved.config.provider == "codex" and skill_names:
        skills_block = inline_skills_for_codex(skill_names)
        if skills_block:
            prompt = f"{skills_block}\n\n---\n\n{prompt}"

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
        project_slug=proj_slug,
        spawn_defaults=resolved,
        resume=resume,
    )
