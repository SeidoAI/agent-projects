"""Git helper functions for worktree and branch operations."""

import subprocess
from pathlib import Path

import pytest

from tripwire.core.git_helpers import (
    RebaseConflict,
    branch_exists,
    fetch_origin,
    rebase_branch_onto,
    worktree_add,
    worktree_is_dirty,
    worktree_list,
    worktree_path_for_session,
    worktree_remove,
)


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
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


class TestBranchExists:
    def test_default_branch_exists(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        # At least one of main/master should exist
        assert branch_exists(repo, "main") or branch_exists(repo, "master")

    def test_nonexistent_branch(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        assert branch_exists(repo, "does-not-exist") is False

    def test_created_branch(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        subprocess.run(["git", "branch", "feat/test"], cwd=repo, check=True)
        assert branch_exists(repo, "feat/test") is True


class TestWorktreePathForSession:
    def test_path_convention(self, tmp_path):
        clone = tmp_path / "projects" / "tripwire"
        clone.mkdir(parents=True)
        result = worktree_path_for_session(clone, "api-endpoints")
        assert result == clone.resolve().parent / "worktree-tripwire-api-endpoints"

    def test_name_suffix(self, tmp_path):
        clone = tmp_path / "myrepo"
        clone.mkdir()
        result = worktree_path_for_session(clone, "auth-spike")
        assert result.name == "worktree-myrepo-auth-spike"


class TestWorktreeAdd:
    def test_creates_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        assert wt_path.is_dir()
        assert (wt_path / ".git").exists()

    def test_branch_created(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        assert branch_exists(repo, "feat/test")


class TestWorktreeRemove:
    def test_removes_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        worktree_remove(repo, wt_path)
        assert not wt_path.exists()

    def test_remove_nonexistent_is_noop(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        worktree_remove(repo, tmp_path / "nope")


class TestWorktreeList:
    def test_lists_created_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        paths = worktree_list(repo)
        resolved = [str(p) for p in paths]
        assert str(wt_path.resolve()) in resolved or str(wt_path) in resolved


class TestWorktreeIsDirty:
    def test_clean_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        assert worktree_is_dirty(wt_path) is False

    def test_dirty_worktree(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_repo(repo)
        wt_path = tmp_path / "repo-wt-test"
        worktree_add(repo, wt_path, "feat/test", "HEAD")
        (wt_path / "new.txt").write_text("uncommitted")
        assert worktree_is_dirty(wt_path) is True


def _commit(
    path: Path, msg: str, *, file: str = "f.txt", content: str | None = None
) -> None:
    """Add a commit with a unique file change."""
    target = path / file
    target.write_text(content if content is not None else msg, encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", file], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "-C",
            str(path),
            "commit",
            "-q",
            "-m",
            msg,
        ],
        check=True,
    )


class TestRebaseBranchOnto:
    """v0.12: helpers used by session_transition_cmd to keep PT branches
    fresh on transitions to in_review (kb-pivot wave-1 staleness fix)."""

    def test_rebase_clean_advances_branch(self, tmp_path):
        # Set up an "origin" repo and a clone with a local branch that
        # has diverged (origin advanced; local has its own commits).
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)

        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", "t"], check=True
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", "t@t"], check=True
        )
        # Initial commit on main (so origin has a tip).
        _commit(clone, "initial")
        subprocess.run(["git", "-C", str(clone), "branch", "-M", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "push", "-q", "-u", "origin", "main"], check=True
        )

        # Branch off, add local commit.
        wt = tmp_path / "feature-wt"
        worktree_add(clone, wt, "feat/x", "main")
        _commit(wt, "feature work", file="g.txt")

        # Advance origin/main with an unrelated commit.
        _commit(clone, "main advances", file="h.txt")
        subprocess.run(
            ["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True
        )

        # Fetch + rebase the feature worktree.
        fetch_origin(wt)
        rebase_branch_onto(wt, "origin/main")

        # The feature worktree's HEAD should now contain both commits
        # (origin/main's "main advances" and feature's "feature work").
        log = subprocess.run(
            ["git", "-C", str(wt), "log", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        assert log[0] == "feature work"
        assert "main advances" in log
        assert "initial" in log

    def test_rebase_conflict_raises_and_aborts(self, tmp_path):
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)

        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", "t"], check=True
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", "t@t"], check=True
        )
        # Shared file, then divergent edits on main vs feature branch.
        _commit(clone, "initial", file="conflict.txt", content="base\n")
        subprocess.run(["git", "-C", str(clone), "branch", "-M", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "push", "-q", "-u", "origin", "main"], check=True
        )

        wt = tmp_path / "feature-wt"
        worktree_add(clone, wt, "feat/conflict", "main")
        _commit(wt, "feature edit", file="conflict.txt", content="feature change\n")

        # Advance origin/main with an incompatible edit on the same file.
        _commit(clone, "main edit", file="conflict.txt", content="main change\n")
        subprocess.run(
            ["git", "-C", str(clone), "push", "-q", "origin", "main"], check=True
        )

        fetch_origin(wt)
        with pytest.raises(RebaseConflict):
            rebase_branch_onto(wt, "origin/main")

        # After conflict, the rebase has been aborted — HEAD should be
        # back on the feature commit, not in a "REBASE_HEAD" state.
        rebase_state = (wt / ".git" / "rebase-merge").exists() or (
            wt / ".git" / "rebase-apply"
        ).exists()
        # `wt/.git` is a file (worktree pointer), so check the actual git dir.
        gitdir_file = (wt / ".git").read_text() if (wt / ".git").is_file() else ""
        # If rebase aborted cleanly, no rebase-merge directory should remain.
        # We verify indirectly by confirming HEAD points to feature edit:
        head_subject = subprocess.run(
            ["git", "-C", str(wt), "log", "-1", "--format=%s"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert head_subject == "feature edit"
        # Suppress unused-variable warnings.
        _ = (rebase_state, gitdir_file)

    def test_fetch_origin_runs_quietly(self, tmp_path):
        origin = tmp_path / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
        clone = tmp_path / "clone"
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.name", "t"], check=True
        )
        subprocess.run(
            ["git", "-C", str(clone), "config", "user.email", "t@t"], check=True
        )
        _commit(clone, "initial")
        subprocess.run(["git", "-C", str(clone), "branch", "-M", "main"], check=True)
        subprocess.run(
            ["git", "-C", str(clone), "push", "-q", "-u", "origin", "main"], check=True
        )
        # Should not raise.
        fetch_origin(clone)
