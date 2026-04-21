"""Tests for pause, abandon, cleanup session lifecycle commands."""

import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


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


class TestSessionPause:
    def test_pause_executing_session(self, tmp_path_project, save_test_session):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={"pid": proc.pid, "claude_session_id": "abc"},
        )
        try:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["pause", "s1", "--project-dir", str(tmp_path_project)],
            )
            assert result.exit_code == 0, result.output
            s = load_session(tmp_path_project, "s1")
            assert s.status == "paused"
        finally:
            proc.kill()
            proc.wait()

    def test_pause_rejects_non_executing(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["pause", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0

    def test_pause_dead_process_sets_failed(self, tmp_path_project, save_test_session):
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={"pid": 4_000_000, "claude_session_id": "abc"},
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["pause", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        s = load_session(tmp_path_project, "s1")
        assert s.status == "failed"


class TestSessionAbandon:
    def test_abandon_planned(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"

    def test_abandon_rejects_completed(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="completed")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0

    def test_abandon_executing_kills_process(self, tmp_path_project, save_test_session):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        save_test_session(
            tmp_path_project,
            "s1",
            status="executing",
            runtime_state={"pid": proc.pid, "claude_session_id": "abc"},
        )
        try:
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["abandon", "s1", "--project-dir", str(tmp_path_project)],
            )
            assert result.exit_code == 0, result.output
            s = load_session(tmp_path_project, "s1")
            assert s.status == "abandoned"
        finally:
            proc.kill()
            proc.wait()


class TestSessionCleanup:
    def test_cleanup_removes_completed_worktree(
        self, tmp_path, tmp_path_project, save_test_session
    ):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "worktree",
                "add",
                str(wt_path),
                "-b",
                "feat/s1",
                "HEAD",
            ],
            check=True,
            capture_output=True,
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "X/Y",
                        "clone_path": str(clone),
                        "worktree_path": str(wt_path),
                        "branch": "feat/s1",
                    }
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0, result.output
        assert not wt_path.exists()

    def test_cleanup_skips_failed(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "worktree",
                "add",
                str(wt_path),
                "-b",
                "feat/s1",
                "HEAD",
            ],
            check=True,
            capture_output=True,
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="failed",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "X/Y",
                        "clone_path": str(clone),
                        "worktree_path": str(wt_path),
                        "branch": "feat/s1",
                    }
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert wt_path.exists()

    def test_cleanup_explicit_id(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "worktree",
                "add",
                str(wt_path),
                "-b",
                "feat/s1",
                "HEAD",
            ],
            check=True,
            capture_output=True,
        )
        save_test_session(
            tmp_path_project,
            "s1",
            status="failed",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "X/Y",
                        "clone_path": str(clone),
                        "worktree_path": str(wt_path),
                        "branch": "feat/s1",
                    }
                ]
            },
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["cleanup", "s1", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert not wt_path.exists()

    def test_cleanup_refuses_dirty(self, tmp_path, tmp_path_project, save_test_session):
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)
        wt_path = tmp_path / "clone-wt-s1"
        subprocess.run(
            [
                "git",
                "-C",
                str(clone),
                "worktree",
                "add",
                str(wt_path),
                "-b",
                "feat/s1",
                "HEAD",
            ],
            check=True,
            capture_output=True,
        )
        (wt_path / "dirty.txt").write_text("uncommitted")
        subprocess.run(["git", "add", "dirty.txt"], cwd=wt_path, check=True)

        save_test_session(
            tmp_path_project,
            "s1",
            status="completed",
            runtime_state={
                "worktrees": [
                    {
                        "repo": "X/Y",
                        "clone_path": str(clone),
                        "worktree_path": str(wt_path),
                        "branch": "feat/s1",
                    }
                ]
            },
        )
        runner = CliRunner()
        runner.invoke(
            session_cmd,
            ["cleanup", "--project-dir", str(tmp_path_project)],
        )
        assert wt_path.exists()


class TestSessionQueue:
    def test_queue_sets_status(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True)
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        assert s.status == "queued"

    def test_queue_rejects_non_planned(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=True, status="completed")
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code != 0

    def test_queue_fails_without_plan(
        self, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        save_test_session(tmp_path_project, "s1", plan=False)
        write_handoff_yaml(tmp_path_project, "s1")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd, ["queue", "s1", "--project-dir", str(tmp_path_project)]
        )
        assert result.exit_code != 0


class TestSessionAgenda:
    def test_agenda_empty_project(self, tmp_path_project):
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "no sessions" in result.output.lower()

    def test_agenda_shows_launchable(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(tmp_path_project, "s2", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "s1" in result.output
        assert "s2" in result.output
        assert "LAUNCHABLE" in result.output

    def test_agenda_shows_blocked(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(
            tmp_path_project,
            "s2",
            status="planned",
            blocked_by_sessions=["s1"],
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "BLOCKED" in result.output

    def test_agenda_json_format(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="planned")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project), "--format", "json"],
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert "sessions" in data
        assert "recommendations" in data

    def test_agenda_all_completed(self, tmp_path_project, save_test_session):
        save_test_session(tmp_path_project, "s1", status="completed")
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "all sessions complete" in result.output.lower()

    def test_agenda_cycle_exits_nonzero(self, tmp_path_project, save_test_session):
        save_test_session(
            tmp_path_project,
            "s1",
            status="planned",
            blocked_by_sessions=["s2"],
        )
        save_test_session(
            tmp_path_project,
            "s2",
            status="planned",
            blocked_by_sessions=["s1"],
        )
        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code != 0
        assert "cycle" in result.output.lower()
