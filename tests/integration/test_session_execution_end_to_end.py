"""End-to-end test for session execution modes.

Exercises the subprocess runtime against a fake-claude shim: spawn
runs prep (worktree, skill copy, CLAUDE.md, kickoff.md), launches
claude via Popen, attach returns the tail-f log argv, abandon sends
SIGTERM. No tmux dependency; no real claude invocation.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from tripwire.cli.session import session_cmd
from tripwire.core.session_store import load_session


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


def _install_fake_claude(tmp_path: Path, monkeypatch) -> Path:
    """Fake claude that prints a few lines then idles for 30s so the
    test can observe lifecycle without burning real budget."""
    bin_dir = tmp_path / "claudebin"
    bin_dir.mkdir()
    fake = bin_dir / "claude"
    fake.write_text('#!/bin/sh\necho "fake-claude ready"\nexec sleep 30\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return fake


def test_subprocess_mode_end_to_end(
    tmp_path,
    tmp_path_project,
    save_test_session,
    write_handoff_yaml,
    monkeypatch,
):
    _install_fake_claude(tmp_path, monkeypatch)

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
        assert session.status == "executing"
        assert session.runtime_state.pid is not None
        assert session.runtime_state.log_path is not None
        assert session.runtime_state.claude_session_id is not None

        # Prep artifacts in the code worktree.
        wt = Path(session.runtime_state.worktrees[0].worktree_path)
        assert (wt / "CLAUDE.md").is_file()
        assert (wt / ".claude/skills/backend-development/SKILL.md").is_file()
        assert (wt / ".tripwire/kickoff.md").is_file()

        # Log file created, fake-claude's "ready" line landed in it.
        # Give the subprocess a brief moment to flush stdout.
        deadline = time.monotonic() + 3.0
        log_path = Path(session.runtime_state.log_path)
        while time.monotonic() < deadline:
            if log_path.is_file() and log_path.read_text():
                break
            time.sleep(0.1)
        assert log_path.is_file()
        log_content = log_path.read_text()
        assert "fake-claude ready" in log_content

        # Attach returns a tail-f AttachExec pointing at the log.
        from tripwire.core.spawn_config import load_resolved_spawn_config
        from tripwire.runtimes import get_runtime
        from tripwire.runtimes.base import AttachExec

        spawn_cfg = load_resolved_spawn_config(tmp_path_project, session=session)
        runtime = get_runtime(spawn_cfg.invocation.runtime)
        cmd = runtime.attach_command(session)
        assert isinstance(cmd, AttachExec)
        assert cmd.argv[0] == "tail"
        assert "-f" in cmd.argv
        assert str(log_path) in cmd.argv

        # Abandon terminates the fake-claude subprocess.
        abandon = runner.invoke(
            session_cmd,
            ["abandon", "s1", "--project-dir", str(tmp_path_project)],
            catch_exceptions=False,
        )
        assert abandon.exit_code == 0, abandon.output

        # Process is gone (or at most in the process of exiting).
        deadline = time.monotonic() + 3.0
        pid = session.runtime_state.pid
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                break
        # If still alive at deadline, force-kill to clean up.
        try:
            os.kill(pid, 0)
            os.kill(pid, 9)
        except ProcessLookupError:
            pass

        s = load_session(tmp_path_project, "s1")
        assert s.status == "abandoned"
    finally:
        # Defensive cleanup in case the test errored before abandon.
        pid = load_session(tmp_path_project, "s1").runtime_state.pid
        if pid:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
