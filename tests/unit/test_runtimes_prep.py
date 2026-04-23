"""Tests for the runtime prep pipeline."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "--allow-empty", "-q", "-m", "init",
        ],
        cwd=path, check=True,
    )


class TestResolveWorktrees:
    def test_creates_one_worktree_per_repo(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.runtimes.prep import resolve_worktrees

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        project_clone = tmp_path / "project-clone"
        project_clone.mkdir()
        _init_repo(project_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        def fake_resolve(_resolved: Path, repo: str) -> Path:
            return code_clone if repo == "SeidoAI/code" else project_clone

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            side_effect=fake_resolve,
        ):
            entries = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
            )

        assert len(entries) == 2
        assert entries[0].repo == "SeidoAI/code"
        assert entries[1].repo == "SeidoAI/project"
        for entry in entries:
            assert Path(entry.worktree_path).is_dir()

    def test_first_repo_is_the_code_worktree(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.runtimes.prep import resolve_worktrees

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            entries = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
            )

        assert entries[0].repo == "SeidoAI/code"

    def test_missing_clone_path_errors(
        self, tmp_path_project, save_test_session
    ):
        from tripwire.runtimes.prep import resolve_worktrees

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[{"repo": "SeidoAI/missing", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="No local clone"):
                resolve_worktrees(
                    session=session,
                    project_dir=tmp_path_project,
                    branch="feat/s1",
                    base_ref="main",
                )


class TestCopySkills:
    def test_copies_named_skills_into_claude_skills(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        skill_md = worktree / ".claude" / "skills" / "backend-development" / "SKILL.md"
        assert skill_md.is_file()

    def test_copies_multiple_skills(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development", "verification"],
        )

        assert (worktree / ".claude/skills/backend-development/SKILL.md").is_file()
        assert (worktree / ".claude/skills/verification/SKILL.md").is_file()

    def test_missing_skill_raises(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        with pytest.raises(RuntimeError, match="no-such-skill"):
            copy_skills(
                worktree=worktree,
                skill_names=["no-such-skill"],
            )

    def test_existing_skills_dir_backed_up(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()
        existing = worktree / ".claude" / "skills"
        existing.mkdir(parents=True)
        (existing / "marker.txt").write_text("old")

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        backups = list(worktree.glob(".claude/skills.bak.*"))
        assert len(backups) == 1
        assert (backups[0] / "marker.txt").read_text() == "old"
        assert (
            worktree / ".claude/skills/backend-development/SKILL.md"
        ).is_file()

    def test_appends_to_git_info_exclude(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").write_text("# existing\n")

        copy_skills(
            worktree=worktree,
            skill_names=["backend-development"],
        )

        exclude = (worktree / ".git" / "info" / "exclude").read_text()
        assert ".claude/" in exclude
        assert ".tripwire/" in exclude
        assert "# existing" in exclude

    def test_git_info_exclude_idempotent(self, tmp_path):
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(worktree=worktree, skill_names=["backend-development"])
        copy_skills(worktree=worktree, skill_names=["backend-development"])

        exclude = (worktree / ".git" / "info" / "exclude").read_text()
        assert exclude.count(".claude/") == 1
        assert exclude.count(".tripwire/") == 1


class TestRenderClaudeMd:
    def test_renders_with_skill_and_worktree_refs(self, tmp_path):
        from tripwire.models.session import WorktreeEntry
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()

        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path=str(tmp_path / "code-clone"),
                    worktree_path=str(code_wt),
                    branch="feat/s1",
                ),
                WorktreeEntry(
                    repo="SeidoAI/project-tracking",
                    clone_path=str(tmp_path / "project-clone"),
                    worktree_path=str(project_wt),
                    branch="feat/s1",
                ),
            ],
            session_id="s1",
        )

        out = (code_wt / "CLAUDE.md").read_text()
        assert "backend-coder" in out
        assert ".claude/skills/backend-development/SKILL.md" in out
        assert str(project_wt) in out
        assert "s1" in out

    def test_existing_claude_md_backed_up(self, tmp_path):
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        (code_wt / "CLAUDE.md").write_text("OLD")

        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=[],
            worktrees=[],
            session_id="s1",
        )

        backups = list(code_wt.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 1
        assert backups[0].read_text() == "OLD"


class TestRenderClaudeMdIdempotency:
    """Mirror of TestCopySkillsIdempotency for CLAUDE.md. Each resume
    used to create a fresh CLAUDE.md.bak.<ts> file — this class guards
    against that regression (bug #2)."""

    def test_idempotent_when_unchanged(self, tmp_path):
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()

        kwargs = {
            "code_worktree": code_wt,
            "agent_id": "backend-coder",
            "skill_names": ["backend-development"],
            "worktrees": [],
            "session_id": "s1",
        }
        render_claude_md(**kwargs)
        render_claude_md(**kwargs)
        render_claude_md(**kwargs)

        backups = list(code_wt.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 0
        assert (code_wt / "CLAUDE.md").is_file()

    def test_backed_up_on_skill_change(self, tmp_path):
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()

        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=["backend-development"],
            worktrees=[],
            session_id="s1",
        )
        render_claude_md(
            code_worktree=code_wt,
            agent_id="backend-coder",
            skill_names=["backend-development", "verification"],
            worktrees=[],
            session_id="s1",
        )

        backups = list(code_wt.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 1

    def test_backed_up_on_template_version_bump(self, tmp_path, monkeypatch):
        """Bumping the template version constant invalidates the
        sentinel hash and forces a re-render — even when all other
        inputs are identical."""
        from tripwire.runtimes import prep as prep_mod
        from tripwire.runtimes.prep import render_claude_md

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()

        kwargs = {
            "code_worktree": code_wt,
            "agent_id": "backend-coder",
            "skill_names": [],
            "worktrees": [],
            "session_id": "s1",
        }
        render_claude_md(**kwargs)
        assert list(code_wt.glob("CLAUDE.md.bak.*")) == []

        monkeypatch.setattr(
            prep_mod, "_CLAUDE_MD_TEMPLATE_VERSION", "bumped"
        )
        render_claude_md(**kwargs)

        backups = list(code_wt.glob("CLAUDE.md.bak.*"))
        assert len(backups) == 1


class TestRenderKickoff:
    def test_writes_kickoff_md(self, tmp_path):
        from tripwire.runtimes.prep import render_kickoff

        code_wt = tmp_path / "wt"
        code_wt.mkdir()

        render_kickoff(code_worktree=code_wt, prompt="do the thing")

        kickoff = code_wt / ".tripwire" / "kickoff.md"
        assert kickoff.is_file()
        assert kickoff.read_text() == "do the thing"


class TestPrepRun:
    def test_end_to_end(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        import yaml as _yaml

        from tripwire.runtimes import RUNTIMES
        from tripwire.runtimes.prep import run as prep_run

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        agents_dir = tmp_path_project / "agents"
        agents_dir.mkdir(exist_ok=True)
        (agents_dir / "backend-coder.yaml").write_text(
            _yaml.safe_dump({
                "id": "backend-coder",
                "context": {"skills": ["backend-development"]},
            })
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            prepped = prep_run(
                session=session,
                project_dir=tmp_path_project,
                runtime=RUNTIMES["manual"],
            )

        assert prepped.session_id == "s1"
        assert prepped.code_worktree.is_dir()
        assert (prepped.code_worktree / "CLAUDE.md").is_file()
        assert (
            prepped.code_worktree / ".claude/skills/backend-development/SKILL.md"
        ).is_file()
        assert (prepped.code_worktree / ".tripwire/kickoff.md").is_file()
        assert prepped.prompt
        assert prepped.claude_session_id
        # project_slug is populated from the tmp_path_project fixture
        # (project.yaml name: "tmp") — guards against regression to the
        # getattr-default "unknown" sink.
        assert prepped.project_slug == "tmp"


class TestResolveWorktreesResume:
    def test_resume_reuses_existing_worktree(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        """resume=True must not error when the worktree already exists —
        it reuses the existing one. Regression test for B1."""
        from tripwire.runtimes.prep import resolve_worktrees

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="paused",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        # First pass creates the worktree
        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            entries = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
            )
        assert len(entries) == 1
        first_path = entries[0].worktree_path

        # Second pass with resume=True reuses the same worktree
        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            entries2 = resolve_worktrees(
                session=session,
                project_dir=tmp_path_project,
                branch="feat/s1",
                base_ref="main",
                resume=True,
            )
        assert len(entries2) == 1
        assert entries2[0].worktree_path == first_path

    def test_resume_errors_when_worktree_vanished(
        self, tmp_path_project, save_test_session
    ):
        from tripwire.runtimes.prep import resolve_worktrees

        save_test_session(
            tmp_path_project,
            "s1",
            status="paused",
            repos=[{"repo": "SeidoAI/missing", "base_branch": "main"}],
        )

        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=None,
        ):
            with pytest.raises(RuntimeError, match="No local clone"):
                resolve_worktrees(
                    session=session,
                    project_dir=tmp_path_project,
                    branch="feat/s1",
                    base_ref="main",
                    resume=True,
                )


class TestBuildClaudeArgsResumePropagation:
    def test_subprocess_runtime_passes_resume_flag(self, tmp_path):
        """SubprocessRuntime.start must thread resume through
        build_claude_args so claude -p --resume <uuid> is invoked."""
        from unittest.mock import MagicMock

        from tripwire.models.session import AgentSession, WorktreeEntry
        from tripwire.models.spawn import SpawnDefaults
        from tripwire.runtimes import SubprocessRuntime
        from tripwire.runtimes.base import PreppedSession

        wt_dir = tmp_path / "wt"
        wt_dir.mkdir()
        wt = WorktreeEntry(
            repo="SeidoAI/code",
            clone_path=str(tmp_path / "clone"),
            worktree_path=str(wt_dir),
            branch="feat/s1",
        )
        prepped = PreppedSession(
            session_id="s1",
            session=AgentSession(id="s1", name="test", agent="a"),
            project_dir=tmp_path,
            code_worktree=wt_dir,
            worktrees=[wt],
            claude_session_id="uuid-1",
            prompt="RESUMING",
            system_append="",
            project_slug="test-proj",
            spawn_defaults=SpawnDefaults.model_validate({
                "prompt_template": "{plan}",
                "resume_prompt_template": "resuming",
                "system_prompt_append": "",
                "invocation": {
                    "log_path_template": str(tmp_path / "logs" / "{session_id}.log"),
                },
            }),
            resume=True,
        )

        fake_proc = MagicMock()
        fake_proc.pid = 12345
        with patch(
            "tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc
        ) as mock_popen:
            SubprocessRuntime().start(prepped)

        argv = mock_popen.call_args[0][0]
        assert "--resume" in argv
        assert argv[argv.index("--resume") + 1] == "uuid-1"
        assert "--session-id" not in argv


class TestPrepRunResume:
    def test_resume_uses_resume_template_and_does_not_read_plan(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        """On resume, prep.run renders the short continuation template
        instead of the full {plan} kickoff, and does NOT require plan.md
        on disk — claude has the prior conversation history."""
        from tripwire.runtimes import RUNTIMES
        from tripwire.runtimes.prep import run as prep_run

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)

        # Note: plan=False so plan.md is deliberately absent. Initial
        # spawn would error; resume must not.
        save_test_session(
            tmp_path_project,
            "s1",
            plan=False,
            status="paused",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        # First create the worktree by running a non-resume prep
        # attempt, then ... no, simpler: use resume=True directly. The
        # worktree gets created here; real resume paths would have an
        # existing one.
        from tripwire.core.session_store import load_session

        session = load_session(tmp_path_project, "s1")

        with patch(
            "tripwire.runtimes.prep._resolve_clone_path",
            return_value=code_clone,
        ):
            # Prime the worktree first (non-resume to create it).
            # But plan.md is absent — so we have to write a stub.
            from tripwire.core.paths import session_plan_path

            plan_path = session_plan_path(tmp_path_project, "s1")
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            plan_path.write_text("# Plan\n", encoding="utf-8")

            prep_run(
                session=session,
                project_dir=tmp_path_project,
                runtime=RUNTIMES["manual"],
            )

            # Now remove plan.md to prove resume doesn't read it.
            plan_path.unlink()

            prepped = prep_run(
                session=session,
                project_dir=tmp_path_project,
                runtime=RUNTIMES["manual"],
                resume=True,
            )

        # Resume prompt contains the distinctive marker, not a plan body.
        assert "Resuming session" in prepped.prompt
        assert prepped.resume is True
        # kickoff.md reflects the resume prompt, not the initial one.
        kickoff = (prepped.code_worktree / ".tripwire" / "kickoff.md").read_text()
        assert "Resuming session" in kickoff


class TestCopySkillsIdempotency:
    def test_unchanged_skill_set_does_not_back_up(self, tmp_path):
        """Re-copying the same skill set must not create a new
        .claude/skills.bak.<ts>/ directory each time (M10)."""
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(worktree=worktree, skill_names=["backend-development"])
        copy_skills(worktree=worktree, skill_names=["backend-development"])
        copy_skills(worktree=worktree, skill_names=["backend-development"])

        backups = list(worktree.glob(".claude/skills.bak.*"))
        assert len(backups) == 0

    def test_changed_skill_set_triggers_backup(self, tmp_path):
        """A genuine change to skill_names does back up the old set."""
        from tripwire.runtimes.prep import copy_skills

        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git" / "info").mkdir(parents=True)
        (worktree / ".git" / "info" / "exclude").touch()

        copy_skills(worktree=worktree, skill_names=["backend-development"])
        copy_skills(
            worktree=worktree,
            skill_names=["backend-development", "verification"],
        )

        backups = list(worktree.glob(".claude/skills.bak.*"))
        assert len(backups) == 1
        # New set in place.
        assert (
            worktree / ".claude/skills/verification/SKILL.md"
        ).is_file()
