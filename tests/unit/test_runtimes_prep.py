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
