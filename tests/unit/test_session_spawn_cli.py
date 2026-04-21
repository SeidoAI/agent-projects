"""Tests for tripwire session spawn."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


def _init_repo(path: Path) -> None:
    # `-b main` makes the initial branch deterministic regardless of
    # `init.defaultBranch`.
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


class TestSessionSpawn:
    def test_spawn_rejects_non_queued(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["spawn", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "queued" in result.output.lower() or "status" in result.output.lower()

    def test_spawn_dry_run_no_side_effects(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[{"repo": "SeidoAI/tripwire", "base_branch": "main"}],
        )
        write_handoff_yaml(tmp_path_project, "s1")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("tripwire.cli.session._resolve_clone_path", return_value=clone),
        ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--dry-run", "--project-dir", str(tmp_path_project)],
            )
        # Dry run should not crash; session stays queued
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"

    def test_spawn_creates_worktree(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        save_test_session(
            tmp_path_project,
            "s1",
            plan=True,
            status="queued",
            repos=[
                {"repo": "SeidoAI/tripwire", "base_branch": "main", "branch": "feat/s1"}
            ],
        )
        write_handoff_yaml(tmp_path_project, "s1", branch="feat/s1")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("tripwire.cli.session._resolve_clone_path", return_value=clone),
            patch("tripwire.cli.session._launch_claude", return_value=99999),
        ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "executing"
        assert len(s.runtime_state.worktrees) == 1
        assert s.runtime_state.pid == 99999
        assert s.runtime_state.claude_session_id is not None

        # Worktree should exist on disk
        wt_path = Path(s.runtime_state.worktrees[0].worktree_path)
        assert wt_path.is_dir()
