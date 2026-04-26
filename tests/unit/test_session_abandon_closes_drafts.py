"""Tests for v0.7.5 A — `tripwire session abandon` closes draft PRs.

When a session is abandoned, any draft PRs opened at session-start are
closed via ``gh pr close`` so they don't pile up as orphan drafts on
the remote. Worktrees without ``draft_pr_url`` (legacy or no-remote
sessions) are skipped silently.
"""

from __future__ import annotations

import subprocess

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


class TestSessionAbandonClosesDrafts:
    def test_calls_gh_pr_close_per_worktree_with_draft_pr_url(
        self, monkeypatch, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt-s1",
                        "branch": "feat/s1",
                        "draft_pr_url": "https://github.com/test/code/pull/10",
                    },
                    {
                        "repo": "example-project",
                        "clone_path": "/tmp/proj",
                        "worktree_path": "/tmp/proj-wt-s1",
                        "branch": "proj/s1",
                        "draft_pr_url": "https://github.com/test/proj/pull/11",
                    },
                ]
            },
        )

        from tripwire.cli import session as session_cli

        calls: list[dict] = []
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            cmd_list = list(cmd)
            calls.append({"cmd": cmd_list, "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            if cmd_list[:3] == ["gh", "pr", "close"]:
                return _R()
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(session_cli.subprocess, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output

        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"

        close_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "close"]]
        assert len(close_calls) == 2
        assert close_calls[0]["cmd"][3] == "https://github.com/test/code/pull/10"
        assert close_calls[1]["cmd"][3] == "https://github.com/test/proj/pull/11"

    def test_skips_worktrees_without_draft_pr_url(
        self, monkeypatch, tmp_path_project, save_test_session
    ):
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "SeidoAI/code",
                        "clone_path": "/tmp/code",
                        "worktree_path": "/tmp/code-wt-s1",
                        "branch": "feat/s1",
                        "draft_pr_url": None,
                    },
                ]
            },
        )

        from tripwire.cli import session as session_cli

        calls: list[dict] = []
        real_run = subprocess.run

        def fake_run(cmd, *args, **kwargs):
            cmd_list = list(cmd)
            calls.append({"cmd": cmd_list, "cwd": kwargs.get("cwd")})

            class _R:
                returncode = 0
                stdout = ""
                stderr = ""

            if cmd_list[:3] == ["gh", "pr", "close"]:
                return _R()
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(session_cli.subprocess, "run", fake_run)

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output

        # No `gh pr close` was attempted for the no-draft worktree.
        close_calls = [c for c in calls if c["cmd"][:3] == ["gh", "pr", "close"]]
        assert close_calls == []
