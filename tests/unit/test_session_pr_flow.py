"""Tests for tripwire.core.session_pr_flow."""

import subprocess
from pathlib import Path

import pytest


def _init_repo_with_commit(path: Path, *, initial_branch: str = "main") -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", initial_branch], cwd=path, check=True
    )
    subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "--allow-empty", "-q", "-m", "init",
        ],
        cwd=path, check=True,
    )


def _add_commit_on_branch(wt: Path, branch: str, marker: str) -> None:
    subprocess.run(
        ["git", "checkout", "-q", "-b", branch], cwd=wt, check=True
    )
    (wt / "marker.txt").write_text(marker)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "add", "marker.txt"],
        cwd=wt, check=True,
    )
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "-m", f"marker: {marker}"],
        cwd=wt, check=True,
    )


class TestRunPrFlowBasic:
    def test_opens_one_pr_per_dirty_worktree(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "code-change")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        _add_commit_on_branch(project_wt, "feat/s1", "project-change")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")

        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        pr_calls = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]
        ]
        assert len(pr_calls) == 2
        assert len(result.pr_urls) == 2
        for url in result.pr_urls:
            assert url.startswith("https://github.com/")

    def test_skips_repo_with_no_new_commits(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "code-change")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"],
            cwd=project_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        pr_calls = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "create"]
        ]
        assert len(pr_calls) == 1
        assert len(result.pr_urls) == 1

    def test_auto_commits_dirty_worktree_when_policy_is_auto(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"],
            cwd=code_wt, check=True,
        )
        (code_wt / "dirty.txt").write_text("uncommitted")
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "dirty.txt"],
            cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            commit_on_complete="auto",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )
        head_log = subprocess.run(
            ["git", "log", "--oneline"],
            cwd=code_wt, capture_output=True, text=True, check=True,
        ).stdout
        assert len(head_log.splitlines()) >= 2
        assert len(result.pr_urls) == 1

    def test_commit_on_complete_manual_aborts_on_dirty(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import PrFlowError, run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        subprocess.run(
            ["git", "checkout", "-q", "-b", "feat/s1"],
            cwd=code_wt, check=True,
        )
        (code_wt / "dirty.txt").write_text("uncommitted")
        subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t",
             "add", "dirty.txt"],
            cwd=code_wt, check=True,
        )

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            commit_on_complete="manual",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")

        with pytest.raises(PrFlowError, match="uncommitted"):
            run_pr_flow(
                session=session,
                project_dir=tmp_path_project,
                skip_push=True,
            )


class TestRunPrFlowCrossLink:
    def test_pr_bodies_cross_link_when_two_prs_open(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        project_wt = tmp_path / "project-wt"
        project_wt.mkdir()
        _init_repo_with_commit(project_wt)
        _add_commit_on_branch(project_wt, "feat/s1", "p")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[
                {"repo": "SeidoAI/code", "base_branch": "main"},
                {"repo": "SeidoAI/project", "base_branch": "main"},
            ],
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    },
                    {
                        "repo": "SeidoAI/project",
                        "clone_path": str(project_wt),
                        "worktree_path": str(project_wt),
                        "branch": "feat/s1",
                    },
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        result = run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        edits = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "edit"]
        ]
        assert len(edits) == len(result.pr_urls) == 2

    def test_merge_policy_await_review_does_not_merge(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="await_review",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]
        ]
        assert merges == []

    def test_merge_policy_auto_on_green_passes_auto_flag(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="auto_merge_on_green",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]
        ]
        assert len(merges) == 1
        joined = " ".join(merges[0])
        assert "--auto" in joined
        assert "--squash" in joined

    def test_merge_policy_auto_immediate_omits_auto_flag(
        self, fake_gh_on_path, tmp_path, tmp_path_project, save_test_session
    ):
        from tripwire.core.session_pr_flow import run_pr_flow
        from tripwire.core.session_store import load_session

        code_wt = tmp_path / "code-wt"
        code_wt.mkdir()
        _init_repo_with_commit(code_wt)
        _add_commit_on_branch(code_wt, "feat/s1", "c")

        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
            merge_policy="auto_merge_immediate",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": str(code_wt),
                        "worktree_path": str(code_wt),
                        "branch": "feat/s1",
                    }
                ],
            },
        )
        session = load_session(tmp_path_project, "s1")
        run_pr_flow(
            session=session,
            project_dir=tmp_path_project,
            skip_push=True,
        )

        merges = [
            c for c in fake_gh_on_path.calls() if c[:2] == ["pr", "merge"]
        ]
        assert len(merges) == 1
        joined = " ".join(merges[0])
        assert "--auto" not in joined
        assert "--squash" in joined
