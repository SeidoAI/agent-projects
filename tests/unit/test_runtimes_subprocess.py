"""Tests for SubprocessRuntime."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from tripwire.models.session import (
    AgentSession,
    RuntimeState,
    WorktreeEntry,
)
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes import SubprocessRuntime
from tripwire.runtimes.base import (
    AttachExec,
    AttachInstruction,
    PreppedSession,
)


def _prepped(tmp_path: Path, *, resume: bool = False) -> PreppedSession:
    wt_dir = tmp_path / "wt"
    wt_dir.mkdir(exist_ok=True)
    wt = WorktreeEntry(
        repo="SeidoAI/code",
        clone_path=str(tmp_path / "clone"),
        worktree_path=str(wt_dir),
        branch="feat/s1",
    )
    return PreppedSession(
        session_id="s1",
        session=AgentSession(id="s1", name="test", agent="a"),
        project_dir=tmp_path,
        code_worktree=wt_dir,
        worktrees=[wt],
        claude_session_id="uuid-1",
        prompt="DO THE THING",
        system_append="",
        spawn_defaults=SpawnDefaults.model_validate(
            {
                "prompt_template": "{plan}",
                "resume_prompt_template": "resuming",
                "system_prompt_append": "",
                "invocation": {
                    "log_path_template": str(tmp_path / "logs" / "{session_id}.log"),
                },
            }
        ),
        resume=resume,
    )


def test_validate_environment_is_noop():
    SubprocessRuntime().validate_environment()


def test_start_invokes_popen_with_expected_argv(tmp_path):
    prepped = _prepped(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 12345

    with patch(
        "tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc
    ) as mock_popen:
        result = SubprocessRuntime().start(prepped)

    mock_popen.assert_called_once()
    argv = mock_popen.call_args[0][0]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "DO THE THING" in argv
    assert "--session-id" in argv  # resume=False → session-id, not --resume
    assert "--resume" not in argv

    # Log file was created + cwd honoured.
    log_path = Path(result.log_path)
    assert log_path.parent.exists()
    kwargs = mock_popen.call_args[1]
    assert kwargs["cwd"] == str(prepped.code_worktree)
    assert kwargs["start_new_session"] is True

    assert result.pid == 12345
    assert result.claude_session_id == "uuid-1"


def test_start_with_resume_uses_resume_flag_not_session_id(tmp_path):
    prepped = _prepped(tmp_path, resume=True)
    fake_proc = MagicMock()
    fake_proc.pid = 67890

    with patch(
        "tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc
    ) as mock_popen:
        SubprocessRuntime().start(prepped)

    argv = mock_popen.call_args[0][0]
    assert "--resume" in argv
    assert argv[argv.index("--resume") + 1] == "uuid-1"
    assert "--session-id" not in argv


def test_pause_sigterms_live_pid(tmp_path):
    session = AgentSession(
        id="s1", name="t", agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with patch(
        "tripwire.runtimes.subprocess.is_alive", return_value=True
    ), patch(
        "tripwire.runtimes.subprocess.send_sigterm"
    ) as mock_sigterm:
        SubprocessRuntime().pause(session)

    mock_sigterm.assert_called_once_with(999)


def test_pause_noop_on_dead_pid():
    session = AgentSession(
        id="s1", name="t", agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with patch(
        "tripwire.runtimes.subprocess.is_alive", return_value=False
    ), patch(
        "tripwire.runtimes.subprocess.send_sigterm"
    ) as mock_sigterm:
        SubprocessRuntime().pause(session)

    mock_sigterm.assert_not_called()


def test_status_reflects_is_alive():
    session = AgentSession(
        id="s1", name="t", agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with patch(
        "tripwire.runtimes.subprocess.is_alive", return_value=True
    ):
        assert SubprocessRuntime().status(session) == "running"

    with patch(
        "tripwire.runtimes.subprocess.is_alive", return_value=False
    ):
        assert SubprocessRuntime().status(session) == "exited"


def test_status_unknown_when_no_pid():
    session = AgentSession(id="s1", name="t", agent="a")
    assert SubprocessRuntime().status(session) == "unknown"


def test_abandon_sigkills_stubborn_process():
    session = AgentSession(
        id="s1", name="t", agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    # is_alive returns True the whole way → forces the SIGKILL branch.
    with patch(
        "tripwire.runtimes.subprocess.is_alive", return_value=True
    ), patch(
        "tripwire.runtimes.subprocess.send_sigterm"
    ), patch(
        "tripwire.runtimes.subprocess.time.sleep"
    ), patch("os.kill") as mock_os_kill:
        SubprocessRuntime().abandon(session)

    mock_os_kill.assert_called_once()
    import signal
    assert mock_os_kill.call_args[0] == (999, signal.SIGKILL)


def test_attach_command_returns_tail_f_on_log():
    session = AgentSession(
        id="s1", name="t", agent="a",
        runtime_state=RuntimeState(
            claude_session_id="uuid-1",
            log_path="/tmp/tripwire-logs/s1-xyz.log",
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path="/tmp/code",
                    worktree_path="/tmp/code-wt",
                    branch="feat/s1",
                ),
            ],
        ),
    )

    cmd = SubprocessRuntime().attach_command(session)

    assert isinstance(cmd, AttachExec)
    assert cmd.argv == ["tail", "-f", "/tmp/tripwire-logs/s1-xyz.log"]


def test_attach_command_returns_instruction_when_no_log_path():
    session = AgentSession(id="s1", name="t", agent="a")
    cmd = SubprocessRuntime().attach_command(session)
    assert isinstance(cmd, AttachInstruction)
    assert "never spawned" in cmd.message.lower() or "no log_path" in cmd.message.lower()
