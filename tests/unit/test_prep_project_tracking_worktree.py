"""Tests for v0.7.4 A2 — per-session project-tracking worktrees.

`maybe_add_project_tracking_worktree` cuts a `proj/<session-slug>`
branch + sibling worktree off the project-tracking repo when it has a
git remote, so parallel sessions don't race on writes to
`sessions/<id>/` or `issues/<KEY>/developer.md`. When there's no
remote, the helper is a logged no-op — pre-v0.7.4 behaviour.

Test patterns: content assertions (path on disk exists, WorktreeEntry
fields equal expected) — not "function didn't raise".
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from tripwire.core.git_helpers import worktree_path_for_session
from tripwire.core.session_store import load_session
from tripwire.runtimes.prep import maybe_add_project_tracking_worktree


def _init_repo(path: Path) -> None:
    """Minimal git repo with one commit — same helper as
    test_runtimes_prep.py."""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        cwd=path,
        check=True,
    )


def _add_fake_remote(path: Path) -> None:
    """Add an `origin` remote pointing at a bogus URL. `gh pr` won't run
    against it, but `git -C <path> remote` returns non-empty, which is
    all the helper checks."""
    subprocess.run(
        ["git", "-C", str(path), "remote", "add", "origin", "git@example.com:x/y.git"],
        check=True,
    )


class TestMaybeAddProjectTrackingWorktree:
    def test_adds_worktree_when_remote_present(
        self, tmp_path_project, save_test_session, caplog
    ):
        _init_repo(tmp_path_project)
        _add_fake_remote(tmp_path_project)
        save_test_session(tmp_path_project, "tst-s1", status="planned")
        session = load_session(tmp_path_project, "tst-s1")

        entry = maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
        )

        assert entry is not None
        expected_wt = worktree_path_for_session(tmp_path_project, session.id)
        assert entry.branch == "proj/tst-s1"
        assert entry.clone_path == str(tmp_path_project)
        assert entry.worktree_path == str(expected_wt)
        assert entry.repo == tmp_path_project.name
        # Content assertion — the worktree directory actually exists
        # on disk with a .git pointer file.
        assert expected_wt.is_dir()
        assert (expected_wt / ".git").exists()

    def test_skips_with_log_when_no_remote(
        self, tmp_path_project, save_test_session, caplog
    ):
        """Initialised git repo, but no remote configured. Helper
        returns None and emits an INFO log explaining the skip."""
        _init_repo(tmp_path_project)
        # Deliberately no _add_fake_remote — `git remote` returns empty.
        save_test_session(tmp_path_project, "tst-s2", status="planned")
        session = load_session(tmp_path_project, "tst-s2")

        caplog.set_level(logging.INFO, logger="tripwire.runtimes.prep")
        entry = maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
        )

        assert entry is None
        expected_wt = worktree_path_for_session(tmp_path_project, session.id)
        # The path was NOT created — skipping must not mutate the fs.
        assert not expected_wt.exists()
        assert any(
            "no git remote" in rec.getMessage() and "tst-s2" in rec.getMessage()
            for rec in caplog.records
        )

    def test_skips_when_not_a_git_repo(
        self, tmp_path_project, save_test_session, caplog
    ):
        """`tmp_path_project` is a plain directory — no .git/. Returns
        None without attempting remote detection."""
        save_test_session(tmp_path_project, "tst-s3", status="planned")
        session = load_session(tmp_path_project, "tst-s3")

        caplog.set_level(logging.INFO, logger="tripwire.runtimes.prep")
        entry = maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
        )

        assert entry is None
        assert any(
            "not a git repo" in rec.getMessage() and "tst-s3" in rec.getMessage()
            for rec in caplog.records
        )

    def test_resume_reuses_existing_worktree(self, tmp_path_project, save_test_session):
        """Idempotent resume: call the helper once, then again with
        resume=True. Second call must succeed without re-creating the
        worktree, returning the same path/branch."""
        _init_repo(tmp_path_project)
        _add_fake_remote(tmp_path_project)
        save_test_session(tmp_path_project, "tst-s4", status="planned")
        session = load_session(tmp_path_project, "tst-s4")

        first = maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
        )
        assert first is not None

        second = maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
            resume=True,
        )
        assert second is not None
        assert first.worktree_path == second.worktree_path
        assert first.branch == second.branch

    def test_refuses_existing_worktree_without_resume(
        self, tmp_path_project, save_test_session
    ):
        """If the worktree already exists and resume is False, the
        helper must refuse — same semantics as resolve_worktrees. A
        stale worktree is an operator error, not silently reused."""
        _init_repo(tmp_path_project)
        _add_fake_remote(tmp_path_project)
        save_test_session(tmp_path_project, "tst-s5", status="planned")
        session = load_session(tmp_path_project, "tst-s5")

        maybe_add_project_tracking_worktree(
            project_dir=tmp_path_project,
            session=session,
        )

        with pytest.raises(RuntimeError, match="already exists"):
            maybe_add_project_tracking_worktree(
                project_dir=tmp_path_project,
                session=session,
            )
