"""Tests for tripwire session spawn."""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


@pytest.fixture(autouse=True)
def _stub_v075_prereqs():
    """Bypass v0.7.5 spawn-time gh + draft-PR prerequisites. These
    tests exercise the spawn CLI; gh/draft-PR mechanics are unit-
    tested separately in ``test_prep_draft_pr.py``."""
    with (
        patch("tripwire.runtimes.prep._check_gh_available"),
        patch("tripwire.runtimes.prep._open_draft_pr", return_value=None),
    ):
        yield


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

        with (
            patch("shutil.which", return_value="/usr/bin/claude"),
            patch(
                "tripwire.cli.session._resolve_clone_path",
                return_value=clone,
            ),
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

    def test_spawn_uses_subprocess_runtime_by_default(
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
        )
        write_handoff_yaml(tmp_path_project, "s1")
        (tmp_path_project / "agents").mkdir(exist_ok=True)
        (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
            "id: backend-coder\ncontext:\n  skills: []\n"
        )

        # Fake claude shim: prints one line, exits. Keeps Popen happy
        # without launching real claude.
        fake_claude = tmp_path / "claudebin"
        fake_claude.mkdir()
        (fake_claude / "claude").write_text("#!/bin/sh\necho ready\n")
        (fake_claude / "claude").chmod(0o755)
        import os as _os

        env_path_override = f"{fake_claude}{_os.pathsep}{_os.environ['PATH']}"

        with (
            patch("shutil.which", return_value=str(fake_claude / "claude")),
            patch(
                "tripwire.cli.session._resolve_clone_path",
                return_value=clone,
            ),
            patch.dict(_os.environ, {"PATH": env_path_override}),
        ):
            runner = CliRunner()
            result = runner.invoke(
                session_cmd,
                ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "s1")
        # Default runtime is subprocess — pid populated, no tmux field.
        assert s.runtime_state.pid is not None
        assert s.runtime_state.log_path is not None
