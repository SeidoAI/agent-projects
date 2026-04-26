"""Git helper functions for worktree and branch operations."""

import subprocess
from pathlib import Path

from tripwire.core.git_helpers import (
    branch_exists,
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
