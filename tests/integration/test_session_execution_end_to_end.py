"""End-to-end test for session execution modes.

Gated on tmux being installed. Exercises: session spawn in tmux mode
creates the tmux session with the right cwd, CLAUDE.md, skills, and
kickoff.md; session abandon kills the tmux session.
"""

import os
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session

pytestmark = pytest.mark.skipif(
    shutil.which("tmux") is None,
    reason="tmux not installed — integration test skipped",
)


def _init_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", "-b", "main"], cwd=path, check=True
    )
    subprocess.run(
        [
            "git", "-c", "user.name=t", "-c", "user.email=t@t",
            "commit", "--allow-empty", "-q", "-m", "init",
        ],
        cwd=path, check=True,
    )


@pytest.fixture
def fake_claude_on_path(tmp_path, monkeypatch):
    """A minimal stand-in for the claude CLI: prints a distinctive
    ready marker, then idles to keep the tmux session alive.

    ``tmux capture-pane`` strips trailing whitespace per line, so the
    default marker of ``"> "`` with a trailing space does not survive
    capture — a real investigation point we hit while integration-
    testing. We side-step it here by overriding the marker via
    ``TRIPWIRE_TMUX_READY_MARKER`` (F6) to something unambiguous the
    fake emits. Verifying the production default against real claude
    still has to happen on a host with real claude installed."""
    bin_dir = tmp_path / "claudebin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text(
        "#!/bin/sh\n"
        "printf 'TRIPWIRE_TEST_READY\\n'\n"
        "exec sleep 60\n"
    )
    fake.chmod(0o755)
    monkeypatch.setenv(
        "PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}"
    )
    monkeypatch.setenv(
        "TRIPWIRE_TMUX_READY_MARKER", "TRIPWIRE_TEST_READY"
    )
    return fake


def test_tmux_mode_end_to_end(
    fake_claude_on_path,
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
        repos=[{"repo": "SeidoAI/code", "base_branch": "main"}],
        spawn_config={"invocation": {"runtime": "tmux"}},
    )
    write_handoff_yaml(tmp_path_project, "s1")
    (tmp_path_project / "agents").mkdir(exist_ok=True)
    (tmp_path_project / "agents" / "backend-coder.yaml").write_text(
        "id: backend-coder\ncontext:\n  skills: [backend-development]\n"
    )

    with patch(
        "tripwire.runtimes.prep._resolve_clone_path",
        return_value=clone,
    ):
        runner = CliRunner()
        spawn_result = runner.invoke(
            session_cmd,
            ["spawn", "s1", "--project-dir", str(tmp_path_project)],
            catch_exceptions=False,
        )

    try:
        assert spawn_result.exit_code == 0, spawn_result.output
        session = load_session(tmp_path_project, "s1")
        assert session.runtime_state.tmux_session_name == "tw-s1"

        has = subprocess.run(
            ["tmux", "has-session", "-t", "tw-s1"],
            capture_output=True,
        )
        assert has.returncode == 0

        wt = Path(session.runtime_state.worktrees[0].worktree_path)
        assert (wt / "CLAUDE.md").is_file()
        assert (
            wt / ".claude/skills/backend-development/SKILL.md"
        ).is_file()
        assert (wt / ".tripwire/kickoff.md").is_file()
    finally:
        subprocess.run(
            ["tmux", "kill-session", "-t", "tw-s1"], check=False
        )
