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
        project_slug="test-proj",
        spawn_defaults=SpawnDefaults.model_validate(
            {
                "prompt_template": "{plan}",
                "resume_prompt_template": "resuming",
                "system_prompt_append": "",
                "invocation": {
                    "log_path_template": str(
                        tmp_path / "logs" / "{project_slug}" / "{session_id}.log"
                    ),
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

    with (
        patch(
            "tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc
        ) as mock_popen,
        patch("tripwire.runtimes.subprocess.spawn_monitor_runner", return_value=None),
    ):
        result = SubprocessRuntime().start(prepped)

    mock_popen.assert_called_once()
    argv = mock_popen.call_args[0][0]
    assert argv[0] == "claude"
    assert "-p" in argv
    assert "DO THE THING" in argv
    assert "--session-id" in argv  # resume=False → session-id, not --resume
    assert "--resume" not in argv

    # Log file was created + cwd honoured + project_slug threaded into path.
    log_path = Path(result.log_path)
    assert log_path.parent.exists()
    assert "test-proj" in str(log_path)
    assert "unknown" not in str(log_path)
    kwargs = mock_popen.call_args[1]
    assert kwargs["cwd"] == str(prepped.code_worktree)
    assert kwargs["start_new_session"] is True

    assert result.pid == 12345
    assert result.claude_session_id == "uuid-1"


def test_start_with_resume_uses_resume_flag_not_session_id(tmp_path):
    prepped = _prepped(tmp_path, resume=True)
    fake_proc = MagicMock()
    fake_proc.pid = 67890

    with (
        patch(
            "tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc
        ) as mock_popen,
        patch("tripwire.runtimes.subprocess.spawn_monitor_runner", return_value=None),
    ):
        SubprocessRuntime().start(prepped)

    argv = mock_popen.call_args[0][0]
    assert "--resume" in argv
    assert argv[argv.index("--resume") + 1] == "uuid-1"
    assert "--session-id" not in argv


def test_start_spawns_monitor_runner_with_agent_pid(tmp_path):
    """The monitor runner is spawned as a detached subprocess with the
    just-launched agent pid. Tripwire #12-#14 enforcement depends on
    this — without the runner, there is no in-flight cost cap."""
    prepped = _prepped(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 4242

    with (
        patch("tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc),
        patch(
            "tripwire.runtimes.subprocess.spawn_monitor_runner",
            return_value=9999,
        ) as mock_spawn_monitor,
    ):
        SubprocessRuntime().start(prepped)

    assert mock_spawn_monitor.called
    cfg = mock_spawn_monitor.call_args.kwargs.get("cfg") or (
        mock_spawn_monitor.call_args.args[0]
        if mock_spawn_monitor.call_args.args
        else None
    )
    assert cfg is not None
    assert cfg.pid == 4242
    assert cfg.session_id == "s1"


def test_start_skips_monitor_when_disabled_in_invocation(tmp_path):
    """spawn_defaults.invocation.monitor=False → no monitor process."""
    prepped = _prepped(tmp_path)
    prepped.spawn_defaults.invocation.monitor = False
    fake_proc = MagicMock()
    fake_proc.pid = 1
    with (
        patch("tripwire.runtimes.subprocess._sp.Popen", return_value=fake_proc),
        patch(
            "tripwire.runtimes.subprocess.spawn_monitor_runner",
            return_value=None,
        ) as mock_spawn_monitor,
    ):
        SubprocessRuntime().start(prepped)
    assert not mock_spawn_monitor.called


def test_pause_sigterms_live_pid(tmp_path):
    """Sanity — pause SIGTERMs then the process exits immediately."""
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    # [True, False]: gate check sees alive → SIGTERM, first poll sees
    # dead → return cleanly.
    with (
        patch(
            "tripwire.runtimes.subprocess.is_alive",
            side_effect=[True, False],
        ),
        patch("tripwire.runtimes.subprocess.send_sigterm") as mock_sigterm,
        patch("tripwire.runtimes.subprocess.time.sleep"),
    ):
        SubprocessRuntime().pause(session)

    mock_sigterm.assert_called_once_with(999)


def test_pause_noop_on_dead_pid():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with (
        patch("tripwire.runtimes.subprocess.is_alive", return_value=False),
        patch("tripwire.runtimes.subprocess.send_sigterm") as mock_sigterm,
    ):
        SubprocessRuntime().pause(session)

    mock_sigterm.assert_not_called()


def test_pause_waits_for_exit():
    """Pause polls is_alive until the process exits. Regression test
    for gap #9 — status used to flip to 'paused' before the process
    was actually gone."""
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    # gate True → sigterm; poll #1 True; poll #2 True; poll #3 False → return.
    alive_iter = iter([True, True, True, False])
    with (
        patch(
            "tripwire.runtimes.subprocess.is_alive",
            side_effect=lambda _pid: next(alive_iter),
        ),
        patch("tripwire.runtimes.subprocess.send_sigterm"),
        patch("tripwire.runtimes.subprocess.time.sleep") as mock_sleep,
    ):
        SubprocessRuntime().pause(session)

    # Two sleeps between the three "alive" poll responses — proves the
    # loop actually polls rather than returning immediately after SIGTERM.
    assert mock_sleep.call_count >= 2


def test_pause_raises_when_sigterm_ignored():
    """If the process ignores SIGTERM for 2s, pause raises so the CLI
    can leave the session in 'executing' rather than lying that it's
    paused."""
    import pytest as _pytest

    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    # monotonic: first call sets deadline base; subsequent calls jump
    # past the 2s window so the loop exits with the process still alive.
    times = iter([0.0, 0.1, 3.0, 3.0])
    with (
        patch("tripwire.runtimes.subprocess.is_alive", return_value=True),
        patch("tripwire.runtimes.subprocess.send_sigterm"),
        patch("tripwire.runtimes.subprocess.time.sleep"),
        patch(
            "tripwire.runtimes.subprocess.time.monotonic",
            side_effect=lambda: next(times),
        ),
    ):
        with _pytest.raises(RuntimeError, match="SIGTERM not honoured"):
            SubprocessRuntime().pause(session)


def test_status_reflects_is_alive():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with patch("tripwire.runtimes.subprocess.is_alive", return_value=True):
        assert SubprocessRuntime().status(session) == "running"

    with patch("tripwire.runtimes.subprocess.is_alive", return_value=False):
        assert SubprocessRuntime().status(session) == "exited"


def test_status_unknown_when_no_pid():
    session = AgentSession(id="s1", name="t", agent="a")
    assert SubprocessRuntime().status(session) == "unknown"


def test_abandon_sigkills_stubborn_process():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    # is_alive returns True the whole way → forces the SIGKILL branch.
    with (
        patch("tripwire.runtimes.subprocess.is_alive", return_value=True),
        patch("tripwire.runtimes.subprocess.send_sigterm"),
        patch("tripwire.runtimes.subprocess.time.sleep"),
        patch("os.kill") as mock_os_kill,
    ):
        SubprocessRuntime().abandon(session)

    mock_os_kill.assert_called_once()
    import signal

    assert mock_os_kill.call_args[0] == (999, signal.SIGKILL)


def test_attach_command_returns_tail_f_on_log():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
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
    assert (
        "never spawned" in cmd.message.lower() or "no log_path" in cmd.message.lower()
    )
