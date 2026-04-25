"""Validator rule `worktree_paths_unique` (v0.7.9 §A9).

No two distinct sessions may claim the same worktree path. Catches
state corruption where two sessions' ``runtime_state.worktrees``
both point at the same physical directory — a race that could
silently overwrite work.
"""

from pathlib import Path

from tripwire.core.validator import load_context
from tripwire.core.validator.lint import worktree_paths_unique


def _wt(repo: str, clone: str, path: str, branch: str) -> dict:
    return {
        "repo": repo,
        "clone_path": clone,
        "worktree_path": path,
        "branch": branch,
    }


def test_two_sessions_same_path_errors(tmp_path_project: Path, save_test_session):
    """Same worktree_path on two sessions → 1 error per shared path."""
    shared = "/tmp/repo-wt-shared"
    save_test_session(
        tmp_path_project,
        "s1",
        runtime_state={
            "worktrees": [
                _wt("o/r", "/tmp/repo", shared, "feat/s1"),
            ]
        },
    )
    save_test_session(
        tmp_path_project,
        "s2",
        runtime_state={
            "worktrees": [
                _wt("o/r", "/tmp/repo", shared, "feat/s2"),
            ]
        },
    )

    ctx = load_context(tmp_path_project)
    results = worktree_paths_unique.check(ctx)

    assert len(results) == 1
    assert results[0].code == "worktree_paths_unique/collision"
    assert results[0].severity == "error"
    msg = results[0].message
    assert shared in msg
    assert "s1" in msg
    assert "s2" in msg


def test_distinct_paths_pass(tmp_path_project: Path, save_test_session):
    save_test_session(
        tmp_path_project,
        "s1",
        runtime_state={"worktrees": [_wt("o/r", "/tmp/repo", "/tmp/wt-1", "feat/s1")]},
    )
    save_test_session(
        tmp_path_project,
        "s2",
        runtime_state={"worktrees": [_wt("o/r", "/tmp/repo", "/tmp/wt-2", "feat/s2")]},
    )

    ctx = load_context(tmp_path_project)
    assert worktree_paths_unique.check(ctx) == []


def test_no_worktrees_passes(tmp_path_project: Path, save_test_session):
    save_test_session(tmp_path_project, "s1")
    save_test_session(tmp_path_project, "s2")

    ctx = load_context(tmp_path_project)
    assert worktree_paths_unique.check(ctx) == []


def test_same_session_multi_repo_no_self_collision(
    tmp_path_project: Path, save_test_session
):
    """A single session with two worktrees (different paths) doesn't
    fire — the rule is about cross-session collisions."""
    save_test_session(
        tmp_path_project,
        "s1",
        runtime_state={
            "worktrees": [
                _wt("o/r1", "/tmp/r1", "/tmp/r1-wt", "feat/s1"),
                _wt("o/r2", "/tmp/r2", "/tmp/r2-wt", "feat/s1"),
            ]
        },
    )

    ctx = load_context(tmp_path_project)
    assert worktree_paths_unique.check(ctx) == []


def test_path_normalization(tmp_path_project: Path, save_test_session):
    """Paths differing only by trailing slash / dup separators still
    collide — they refer to the same directory."""
    save_test_session(
        tmp_path_project,
        "s1",
        runtime_state={
            "worktrees": [_wt("o/r", "/tmp/repo", "/tmp/wt//x/", "feat/s1")]
        },
    )
    save_test_session(
        tmp_path_project,
        "s2",
        runtime_state={"worktrees": [_wt("o/r", "/tmp/repo", "/tmp/wt/x", "feat/s2")]},
    )

    ctx = load_context(tmp_path_project)
    results = worktree_paths_unique.check(ctx)
    assert len(results) == 1
    assert results[0].code == "worktree_paths_unique/collision"


def test_three_sessions_one_collision(tmp_path_project: Path, save_test_session):
    """Three sessions claiming the same path → 1 collision finding
    naming all three."""
    shared = "/tmp/wt-shared"
    for sid in ("s1", "s2", "s3"):
        save_test_session(
            tmp_path_project,
            sid,
            runtime_state={
                "worktrees": [_wt("o/r", "/tmp/repo", shared, f"feat/{sid}")]
            },
        )

    ctx = load_context(tmp_path_project)
    results = worktree_paths_unique.check(ctx)
    assert len(results) == 1
    assert all(sid in results[0].message for sid in ("s1", "s2", "s3"))
