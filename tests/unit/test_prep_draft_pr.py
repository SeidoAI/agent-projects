"""Tests for v0.7.5 A — draft PRs at session-start.

After each ``worktree_add`` the prep pipeline emits an empty marker
commit, pushes ``-u origin``, and runs ``gh pr create --draft``. The
draft PR URL is stored on ``WorktreeEntry.draft_pr_url``. When the
worktree has no git remote the helper logs a warning and returns
``None`` (graceful skip — pre-v0.7.5 sessions stay on the legacy
create-PR-at-complete path). Missing or unauthenticated ``gh``
fails spawn fast at prep time, before any filesystem mutation.
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


def _init_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    # Persist identity on the repo (not via per-command `-c`) so any
    # worktree cut off this repo inherits the config — `_open_draft_pr`
    # makes a real `git commit --allow-empty` on the worktree and would
    # otherwise fail on CI runners with no global gitconfig.
    subprocess.run(["git", "-C", str(path), "config", "user.name", "t"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "t@t"], check=True)
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


def _add_fake_remote(path: Path) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(path),
            "remote",
            "add",
            "origin",
            "git@example.com:x/y.git",
        ],
        check=True,
    )


def _make_worktree_with_branch(tmp_path: Path, branch: str) -> Path:
    wt = tmp_path / "wt"
    wt.mkdir()
    _init_repo(wt)
    _add_fake_remote(wt)
    subprocess.run(
        ["git", "-C", str(wt), "checkout", "-q", "-b", branch],
        check=True,
    )
    return wt


def _selective_subprocess_run(
    calls: list[list[str]],
    *,
    pr_url: str = "https://github.com/test/repo/pull/42",
):
    """Build a side_effect that stubs ``git push`` and ``gh`` while
    letting other git operations run for real."""
    real_run = subprocess.run

    def side_effect(argv, *args, **kwargs):
        argv_list = list(argv)
        calls.append(argv_list)
        if argv_list and argv_list[0] == "git" and "push" in argv_list:
            return subprocess.CompletedProcess(
                args=argv_list, returncode=0, stdout="", stderr=""
            )
        if argv_list and argv_list[0] == "gh":
            if "auth" in argv_list:
                return subprocess.CompletedProcess(
                    args=argv_list, returncode=0, stdout="Logged in.\n", stderr=""
                )
            if "create" in argv_list:
                return subprocess.CompletedProcess(
                    args=argv_list,
                    returncode=0,
                    stdout=pr_url + "\n",
                    stderr="",
                )
            return subprocess.CompletedProcess(
                args=argv_list, returncode=0, stdout="", stderr=""
            )
        return real_run(argv, *args, **kwargs)

    return side_effect


class TestOpenDraftPr:
    def test_emits_marker_commit_then_push_then_gh_pr_create(self, tmp_path):
        from tripwire.runtimes.prep import _open_draft_pr

        wt = _make_worktree_with_branch(tmp_path, "feat/foo")
        calls: list[list[str]] = []

        with patch("subprocess.run", side_effect=_selective_subprocess_run(calls)):
            url = _open_draft_pr(
                worktree=wt,
                branch="feat/foo",
                base_branch="main",
                session_id="tst-s1",
            )

        assert url == "https://github.com/test/repo/pull/42"

        # The empty marker commit lands on feat/foo with the expected message.
        log = subprocess.run(
            ["git", "-C", str(wt), "log", "--oneline", "feat/foo"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "session(tst-s1): start" in log.stdout

        # Order: commit before push, push before gh pr create.
        commit_idx = next(
            i
            for i, c in enumerate(calls)
            if c[:1] == ["git"] and "commit" in c and "--allow-empty" in c
        )
        push_idx = next(
            i for i, c in enumerate(calls) if c[:1] == ["git"] and "push" in c
        )
        gh_idx = next(
            i for i, c in enumerate(calls) if c[:1] == ["gh"] and "create" in c
        )
        assert commit_idx < push_idx < gh_idx

        # gh pr create gets the right --base, --head, and --draft.
        gh_call = calls[gh_idx]
        assert "--draft" in gh_call
        assert "--base" in gh_call
        assert gh_call[gh_call.index("--base") + 1] == "main"
        assert "--head" in gh_call
        assert gh_call[gh_call.index("--head") + 1] == "feat/foo"

    def test_skips_with_warning_when_no_remote(self, tmp_path, caplog):
        from tripwire.runtimes.prep import _open_draft_pr

        wt = tmp_path / "wt"
        wt.mkdir()
        _init_repo(wt)
        # No remote configured.
        subprocess.run(
            ["git", "-C", str(wt), "checkout", "-q", "-b", "feat/foo"],
            check=True,
        )

        calls: list[list[str]] = []
        with caplog.at_level(logging.WARNING, logger="tripwire.runtimes.prep"):
            with patch(
                "subprocess.run",
                side_effect=_selective_subprocess_run(calls),
            ):
                url = _open_draft_pr(
                    worktree=wt,
                    branch="feat/foo",
                    base_branch="main",
                    session_id="tst-s1",
                )

        assert url is None

        # No marker commit was made (no commit/push/gh attempted).
        log = subprocess.run(
            ["git", "-C", str(wt), "log", "--oneline"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "session(tst-s1): start" not in log.stdout

        # No gh or push call was attempted.
        assert not any(c[:1] == ["gh"] for c in calls)
        assert not any(c[:1] == ["git"] and "push" in c for c in calls)

        # Warning logged.
        assert any(
            "no git remote" in r.message.lower()
            or "skipping draft pr" in r.message.lower()
            for r in caplog.records
        )


class TestResolveWorktreesPopulatesDraftPrUrl:
    def test_each_worktree_entry_has_draft_pr_url(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
    ):
        from tripwire.core.session_store import load_session
        from tripwire.runtimes.prep import resolve_worktrees

        code_clone = tmp_path / "code-clone"
        code_clone.mkdir()
        _init_repo(code_clone)
        _add_fake_remote(code_clone)

        save_test_session(
            tmp_path_project,
            "s1",
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        session = load_session(tmp_path_project, "s1")

        calls: list[list[str]] = []
        with patch(
            "tripwire.runtimes.prep._resolve_clone_path", return_value=code_clone
        ):
            with patch("subprocess.run", side_effect=_selective_subprocess_run(calls)):
                entries = resolve_worktrees(
                    session=session,
                    project_dir=tmp_path_project,
                    branch="feat/s1",
                    base_ref="main",
                )

        assert len(entries) == 1
        assert entries[0].draft_pr_url == "https://github.com/test/repo/pull/42"


class TestMaybeAddProjectTrackingWorktreePopulatesDraftPrUrl:
    def test_project_tracking_entry_has_draft_pr_url(
        self,
        tmp_path_project,
        save_test_session,
    ):
        from tripwire.core.session_store import load_session
        from tripwire.runtimes.prep import maybe_add_project_tracking_worktree

        _init_repo(tmp_path_project)
        _add_fake_remote(tmp_path_project)

        save_test_session(tmp_path_project, "tst-s1", status="planned")
        session = load_session(tmp_path_project, "tst-s1")

        calls: list[list[str]] = []
        with patch(
            "subprocess.run",
            side_effect=_selective_subprocess_run(
                calls, pr_url="https://github.com/test/proj/pull/7"
            ),
        ):
            entry = maybe_add_project_tracking_worktree(
                project_dir=tmp_path_project,
                session=session,
            )

        assert entry is not None
        assert entry.draft_pr_url == "https://github.com/test/proj/pull/7"


class TestCheckGhAvailable:
    def test_raises_when_gh_not_on_path(self):
        from tripwire.runtimes.prep import _check_gh_available

        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match=r"gh.*PATH"):
                _check_gh_available()

    def test_raises_when_gh_auth_status_fails(self):
        from tripwire.runtimes.prep import _check_gh_available

        def fake_run(argv, *args, **kwargs):
            if list(argv)[:2] == ["gh", "auth"]:
                return subprocess.CompletedProcess(
                    args=argv, returncode=1, stdout="", stderr="not logged in"
                )
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="", stderr=""
            )

        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run", side_effect=fake_run):
                with pytest.raises(RuntimeError, match=r"auth"):
                    _check_gh_available()

    def test_passes_when_gh_present_and_authenticated(self):
        from tripwire.runtimes.prep import _check_gh_available

        def fake_run(argv, *args, **kwargs):
            return subprocess.CompletedProcess(
                args=argv, returncode=0, stdout="Logged in.\n", stderr=""
            )

        with patch("shutil.which", return_value="/usr/bin/gh"):
            with patch("subprocess.run", side_effect=fake_run):
                # No exception raised.
                _check_gh_available()
