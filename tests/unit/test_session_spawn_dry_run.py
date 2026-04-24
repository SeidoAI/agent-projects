"""Tests for I5 — `session spawn --dry-run` is pure.

v0.7.2's dry-run called prep_run() before checking the dry_run flag.
prep_run() mutates the filesystem (creates the worktree, renders
CLAUDE.md, copies skills). Every subsequent real spawn against the
same session failed with "Worktree already exists".

After I5, dry-run resolves symbolic paths (worktree location,
runtime, max_turns) without invoking prep. No git worktree add, no
file writes, no skills mount.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.git_helpers import worktree_path_for_session


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


def _fake_claude_on_path(tmp_path: Path, monkeypatch):
    """So `session spawn` passes the claude-CLI precondition check."""
    import os

    bin_dir = tmp_path / "claudebin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text("#!/bin/sh\nexit 0\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


class TestDryRunPure:
    def test_dry_run_does_not_create_worktree(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
        monkeypatch,
    ):
        _fake_claude_on_path(tmp_path, monkeypatch)
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        expected_wt = worktree_path_for_session(clone, "s1")
        # Pre-assertion: nothing on disk yet.
        assert not expected_wt.exists()

        runner = CliRunner()
        with patch(
            "tripwire.cli.session._resolve_clone_path",
            return_value=clone,
        ):
            result = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--project-dir",
                    str(tmp_path_project),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        # Path is reported in the output...
        assert str(expected_wt) in result.output
        # ...but does NOT exist on disk — the fix.
        assert not expected_wt.exists()

    def test_dry_run_does_not_render_claude_md_or_skills(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
        monkeypatch,
    ):
        _fake_claude_on_path(tmp_path, monkeypatch)
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        with patch(
            "tripwire.cli.session._resolve_clone_path",
            return_value=clone,
        ):
            result = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--project-dir",
                    str(tmp_path_project),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        expected_wt = worktree_path_for_session(clone, "s1")
        assert not (expected_wt / "CLAUDE.md").exists()
        assert not (expected_wt / ".claude" / "skills").exists()
        assert not (expected_wt / ".tripwire" / "kickoff.md").exists()

    def test_dry_run_then_real_spawn_succeeds(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
        monkeypatch,
    ):
        """The ur-regression — v0.7.2 dry-run left a worktree on disk,
        so the subsequent real spawn failed with "worktree already
        exists". After I5 a real spawn right after dry-run must work."""
        _fake_claude_on_path(tmp_path, monkeypatch)
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )
        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        with (
            patch(
                "tripwire.cli.session._resolve_clone_path",
                return_value=clone,
            ),
            patch(
                "tripwire.runtimes.prep._resolve_clone_path",
                return_value=clone,
            ),
        ):
            dry = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--project-dir",
                    str(tmp_path_project),
                    "--dry-run",
                ],
            )
            assert dry.exit_code == 0, dry.output

            # Real spawn immediately after — must succeed.
            real = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--project-dir",
                    str(tmp_path_project),
                ],
            )
        assert real.exit_code == 0, real.output
        # Real spawn DID create the worktree.
        expected_wt = worktree_path_for_session(clone, "s1")
        assert expected_wt.exists()

    def test_dry_run_shows_unresolved_for_missing_local(
        self, tmp_path_project, save_test_session, write_handoff_yaml, monkeypatch
    ):
        """Repo slug with no `local:` in project.yaml — dry-run reports
        it as unresolved rather than crashing."""
        import os

        bin_dir = tmp_path_project / "claudebin"
        bin_dir.mkdir()
        (bin_dir / "claude").write_text("#!/bin/sh\nexit 0\n")
        (bin_dir / "claude").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/missing", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        runner = CliRunner()
        with patch(
            "tripwire.cli.session._resolve_clone_path",
            return_value=None,
        ):
            result = runner.invoke(
                session_cmd,
                [
                    "spawn",
                    "s1",
                    "--project-dir",
                    str(tmp_path_project),
                    "--dry-run",
                ],
            )

        assert result.exit_code == 0, result.output
        assert "unresolved" in result.output
        assert "SeidoAI/missing" in result.output
