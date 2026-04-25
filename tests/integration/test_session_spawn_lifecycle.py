"""Integration test: full session spawn lifecycle with claude shim."""

import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session, save_session


def _init_repo(path: Path) -> None:
    # Use `-b main` to make the initial branch deterministic — CI runners
    # may have `init.defaultBranch` unset and default to `master`, but the
    # sessions under test pass `base_branch: main` so the repo must have `main`.
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


def _create_claude_shim(tmp_path: Path) -> Path:
    """Create a fake claude script that sleeps briefly and exits 0."""
    shim = tmp_path / "claude"
    shim.write_text(
        textwrap.dedent(f"""\
        #!{sys.executable}
        import time, sys
        time.sleep(2)
        sys.exit(0)
    """)
    )
    shim.chmod(0o755)
    return shim


class TestSpawnLifecycle:
    def test_queue_spawn_pause_cleanup(
        self, tmp_path, tmp_path_project, save_test_session, write_handoff_yaml
    ):
        """Full lifecycle: queue → spawn → pause → cleanup."""
        clone = tmp_path / "clone"
        clone.mkdir()
        _init_repo(clone)

        _create_claude_shim(tmp_path)
        env = {**os.environ, "PATH": f"{tmp_path}:{os.environ.get('PATH', '')}"}

        save_test_session(
            tmp_path_project,
            "lifecycle-test",
            plan=True,
            status="planned",
            repos=[{"repo": "SeidoAI/test", "base_branch": "main"}],
            spawn_config={"invocation": {"runtime": "manual"}},
        )
        write_handoff_yaml(
            tmp_path_project, "lifecycle-test", branch="feat/lifecycle-test"
        )

        runner = CliRunner(env=env)
        pdir = str(tmp_path_project)

        # Queue
        result = runner.invoke(
            session_cmd, ["queue", "lifecycle-test", "--project-dir", pdir]
        )
        assert result.exit_code == 0, result.output
        assert load_session(tmp_path_project, "lifecycle-test").status == "queued"

        # Spawn (with mocked clone resolution). v0.7.5 prep prereqs
        # (gh-availability + draft-PR creation) are unit-tested in
        # `tests/unit/test_prep_draft_pr.py`; bypass them here so the
        # lifecycle flow doesn't depend on the CI runner's gh auth.
        with (
            patch("tripwire.cli.session._resolve_clone_path", return_value=clone),
            patch("tripwire.runtimes.prep._check_gh_available"),
            patch("tripwire.runtimes.prep._open_draft_pr", return_value=None),
        ):
            result = runner.invoke(
                session_cmd, ["spawn", "lifecycle-test", "--project-dir", pdir]
            )

        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "lifecycle-test")
        assert s.status == "executing"
        assert s.runtime_state.claude_session_id is not None
        assert len(s.runtime_state.worktrees) == 1

        # Pause (manual runtime — no process to kill; lifecycle transitions only)
        result = runner.invoke(
            session_cmd, ["pause", "lifecycle-test", "--project-dir", pdir]
        )
        assert result.exit_code == 0, result.output
        s = load_session(tmp_path_project, "lifecycle-test")
        assert s.status in ("paused", "failed")

        # Force to completed for cleanup test
        s.status = "completed"
        save_session(tmp_path_project, s)

        # Cleanup
        result = runner.invoke(session_cmd, ["cleanup", "--project-dir", pdir])
        assert result.exit_code == 0, result.output

    def test_agenda_with_dependencies(self, tmp_path_project, save_test_session):
        """Agenda correctly identifies launchable vs blocked."""
        save_test_session(tmp_path_project, "s1", status="planned")
        save_test_session(
            tmp_path_project,
            "s2",
            status="planned",
            blocked_by_sessions=["s1"],
        )
        save_test_session(tmp_path_project, "s3", status="completed")

        runner = CliRunner()
        result = runner.invoke(
            session_cmd,
            ["agenda", "--project-dir", str(tmp_path_project)],
        )
        assert result.exit_code == 0
        assert "LAUNCHABLE" in result.output
        assert "s1" in result.output
        assert "BLOCKED" in result.output
        assert "s2" in result.output

    def test_abandon_then_cleanup(self, tmp_path, tmp_path_project, save_test_session):
        """Abandon sets status, cleanup removes worktree."""
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
            status="planned",
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
        pdir = str(tmp_path_project)

        # Abandon
        result = runner.invoke(session_cmd, ["abandon", "s1", "--project-dir", pdir])
        assert result.exit_code == 0
        assert load_session(tmp_path_project, "s1").status == "abandoned"

        # Cleanup (abandoned sessions are cleaned by default)
        result = runner.invoke(session_cmd, ["cleanup", "--project-dir", pdir])
        assert result.exit_code == 0
        assert not wt_path.exists()
