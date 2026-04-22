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
            spawn_config={"invocation": {"runtime": "manual"}},
        )
        write_handoff_yaml(tmp_path_project, "s1", branch="feat/s1")

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch("tripwire.cli.session._resolve_clone_path", return_value=clone),
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
        assert s.runtime_state.claude_session_id is not None

        # Worktree should exist on disk
        wt_path = Path(s.runtime_state.worktrees[0].worktree_path)
        assert wt_path.is_dir()


class TestSpawnRuntimeDispatch:
    def test_spawn_uses_manual_runtime_when_configured(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
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
            spawn_config={"invocation": {"runtime": "manual"}},
        )
        write_handoff_yaml(tmp_path_project, "s1")

        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch(
                 "tripwire.cli.session._resolve_clone_path",
                 return_value=clone,
             ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        assert "manual" in result.output.lower()
        assert "claude --name s1" in result.output

        s = load_session(tmp_path_project, "s1")
        assert s.status == "executing"
        assert s.runtime_state.claude_session_id is not None
        assert len(s.runtime_state.worktrees) == 1
        wt = Path(s.runtime_state.worktrees[0].worktree_path)
        assert (wt / "CLAUDE.md").is_file()
        assert (wt / ".tripwire" / "kickoff.md").is_file()

    def test_spawn_uses_tmux_runtime_by_default(
        self,
        fake_tmux_on_path,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
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
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        fake_tmux_on_path.set_pane_text("> ")

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch(
                 "tripwire.cli.session._resolve_clone_path",
                 return_value=clone,
             ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.runtime_state.tmux_session_name == "tw-s1"
        assert s.runtime_state.pid is None

    def test_spawn_errors_when_tmux_missing_and_runtime_is_tmux(
        self,
        tmp_path,
        tmp_path_project,
        save_test_session,
        write_handoff_yaml,
        monkeypatch,
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
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        monkeypatch.setenv("PATH", "/nonexistent-dir")

        with patch(
            "shutil.which",
            lambda x: "/usr/bin/claude" if x == "claude" else None,
        ), patch(
            "tripwire.cli.session._resolve_clone_path",
            return_value=clone,
        ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code != 0
        assert "tmux" in result.output.lower()
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"
