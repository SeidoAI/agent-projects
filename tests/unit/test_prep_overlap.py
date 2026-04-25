"""Regression test for the v0.7.9 §A6 #4 overlap bug.

Pre-fix: ``runtimes/prep.py`` ran ``resolve_worktrees`` (one worktree
per ``session.repos``) and then ``maybe_add_project_tracking_worktree``
which ALWAYS cuts a worktree off ``project_dir``. If
``session.repos[0]``'s clone path resolved to ``project_dir`` itself,
the second call would try to ``git worktree add`` at the same path the
first call had just created → ``fatal: 'X' already exists``.

Post-fix: ``resolve_worktrees`` skips any session.repos entry whose
clone_path equals project_dir; the PT pass creates that single worktree.
Strict-check ``check/repos_overlap`` blocks the configuration upstream
so this only triggers as a defence-in-depth.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tripwire.models.session import AgentSession, RepoBinding
from tripwire.runtimes.prep import resolve_worktrees


def _init_repo(path: Path) -> None:
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


def test_resolve_worktrees_skips_overlap_with_project_dir(tmp_path, monkeypatch):
    """When session.repos[0] resolves to project_dir, resolve_worktrees
    must skip that entry (and return zero entries) — the PT pass cuts
    the only worktree."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _init_repo(project_dir)

    session = AgentSession.model_validate(
        {
            "id": "session-overlap",
            "name": "test",
            "agent": "backend-coder",
            "issues": ["TMP-1"],
            "repos": [{"repo": "self/repo", "base_branch": "main"}],
            "status": "queued",
        }
    )

    # Force _resolve_clone_path to return project_dir — simulating today's
    # bug where session.repos[i].repo's local clone is project_dir.
    monkeypatch.setattr(
        "tripwire.runtimes.prep._resolve_clone_path",
        lambda _proj, _slug: project_dir,
    )
    # Skip draft-PR side effects.
    monkeypatch.setattr("tripwire.runtimes.prep._open_draft_pr", lambda **kw: None)

    entries = resolve_worktrees(
        session=session,
        project_dir=project_dir,
        branch="feat/test",
        base_ref="HEAD",
    )
    assert entries == [], (
        f"expected resolve_worktrees to skip overlapping entry, got {entries}"
    )


def test_resolve_worktrees_keeps_non_overlapping_entry(tmp_path, monkeypatch):
    """Sanity: a session.repo with a clone path DIFFERENT from project_dir
    must still be resolved into a worktree entry."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _init_repo(project_dir)

    other_clone = tmp_path / "other"
    other_clone.mkdir()
    _init_repo(other_clone)

    session = AgentSession.model_validate(
        {
            "id": "session-distinct",
            "name": "test",
            "agent": "backend-coder",
            "issues": ["TMP-1"],
            "repos": [{"repo": "org/code", "base_branch": "main"}],
            "status": "queued",
        }
    )

    monkeypatch.setattr(
        "tripwire.runtimes.prep._resolve_clone_path",
        lambda _proj, _slug: other_clone,
    )
    monkeypatch.setattr("tripwire.runtimes.prep._open_draft_pr", lambda **kw: None)

    entries = resolve_worktrees(
        session=session,
        project_dir=project_dir,
        branch="feat/test",
        base_ref="HEAD",
    )
    assert len(entries) == 1
    assert entries[0].repo == "org/code"


def test_resolve_worktrees_skips_overlap_among_multi_repo_session(
    tmp_path, monkeypatch
):
    """When ONE of multiple session.repos overlaps with project_dir,
    only that one is skipped; the rest resolve normally."""
    project_dir = tmp_path / "proj"
    project_dir.mkdir()
    _init_repo(project_dir)

    other_clone = tmp_path / "other"
    other_clone.mkdir()
    _init_repo(other_clone)

    session = AgentSession.model_validate(
        {
            "id": "session-mixed",
            "name": "test",
            "agent": "backend-coder",
            "issues": ["TMP-1"],
            "repos": [
                # First overlaps; second does not.
                RepoBinding(repo="self/repo", base_branch="main"),
                RepoBinding(repo="org/code", base_branch="main"),
            ],
            "status": "queued",
        }
    )

    def _fake_resolve(_proj, slug):
        return project_dir if slug == "self/repo" else other_clone

    monkeypatch.setattr("tripwire.runtimes.prep._resolve_clone_path", _fake_resolve)
    monkeypatch.setattr("tripwire.runtimes.prep._open_draft_pr", lambda **kw: None)

    entries = resolve_worktrees(
        session=session,
        project_dir=project_dir,
        branch="feat/test",
        base_ref="HEAD",
    )
    assert [e.repo for e in entries] == ["org/code"]
