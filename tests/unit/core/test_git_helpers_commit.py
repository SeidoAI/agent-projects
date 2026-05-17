"""Tests for ``git_helpers.commit_and_push_file``.

The helper is the load-bearing primitive that lands
``runtime_state.claude_session_id`` on the PT branch from
``tripwire session spawn`` (v0.13.2). Without these commits the
field lives only as an uncommitted edit in the main checkout and
gets wiped on the next PR squash-merge — which is the regression
the helper exists to prevent.

Real ``git`` is exercised against a temporary repo (the same
pattern as ``tests/unit/test_prep_draft_pr.py``); the push side is
exercised against a bare local ``origin`` so the helper's success
and failure paths run real subprocess plumbing.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from tripwire.core.git_helpers import commit_and_push_file


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "t"], check=True
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "t@t"], check=True
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "commit",
            "--allow-empty",
            "-q",
            "-m",
            "init",
        ],
        check=True,
    )


def _init_bare(path: Path) -> None:
    subprocess.run(["git", "init", "--bare", "-q", "-b", "main"], cwd=path, check=True)


def _add_upstream(repo: Path, bare: Path) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "remote", "add", "origin", str(bare)], check=True
    )
    subprocess.run(
        ["git", "-C", str(repo), "push", "-q", "-u", "origin", "main"], check=True
    )


# ---------------------------------------------------------------------------


def test_returns_none_when_no_diff(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    target = repo / "f.txt"
    target.write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", str(target)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )

    sha = commit_and_push_file(repo, target, "noop")

    assert sha is None


def test_commits_and_returns_sha(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    bare = tmp_path / "bare.git"
    bare.mkdir()
    _init_bare(bare)
    _add_upstream(repo, bare)

    target = repo / "session.yaml"
    target.write_text("status: planned\n")

    sha = commit_and_push_file(repo, target, "session(X): capture runtime_state")

    assert sha is not None
    assert len(sha) == 40
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == sha
    msg = subprocess.run(
        ["git", "-C", str(repo), "log", "-1", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert msg == "session(X): capture runtime_state"
    # Pushed to bare: the remote tracking ref advances.
    remote = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "origin/main"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert remote == sha


def test_push_failure_logs_warning_but_returns_sha(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    # No upstream configured at all — push will fail.
    target = repo / "session.yaml"
    target.write_text("status: planned\n")

    with caplog.at_level(logging.WARNING, logger="tripwire.core.git_helpers"):
        sha = commit_and_push_file(repo, target, "msg")

    assert sha is not None
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert head == sha
    # Commit landed locally; warning surfaces the failed push.
    assert any("push failed" in r.message for r in caplog.records)


def test_commit_failure_raises(tmp_path: Path) -> None:
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    # Install a pre-commit hook that always fails — simulates a real
    # project hook rejecting the commit. Helper must NOT swallow.
    hooks = repo / ".git" / "hooks"
    hook = hooks / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    target = repo / "session.yaml"
    target.write_text("status: planned\n")

    with pytest.raises(subprocess.CalledProcessError):
        commit_and_push_file(repo, target, "msg")


def test_path_scoped_commit_ignores_other_staged_changes(tmp_path: Path) -> None:
    """Commit is path-scoped: a pre-existing staged but unrelated edit
    in the worktree does NOT get pulled into the runtime_state commit."""
    repo = tmp_path / "r"
    repo.mkdir()
    _init_repo(repo)
    other = repo / "other.txt"
    other.write_text("baseline\n")
    subprocess.run(["git", "-C", str(repo), "add", str(other)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "seed"], check=True
    )

    # Stage an edit to other.txt — should NOT land in the commit below.
    other.write_text("staged-but-uncommitted\n")
    subprocess.run(["git", "-C", str(repo), "add", str(other)], check=True)

    target = repo / "session.yaml"
    target.write_text("status: planned\n")
    sha = commit_and_push_file(repo, target, "session(X): only this file")

    assert sha is not None
    changed = subprocess.run(
        ["git", "-C", str(repo), "show", "--name-only", "--format=", sha],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert "session.yaml" in changed
    assert "other.txt" not in changed
