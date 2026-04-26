"""Tests for CodexRuntime — the OpenAI Codex CLI adapter.

Mirrors the structure of test_runtimes_claude.py: the runtime is a thin
wrapper around `codex exec --json …` (or `codex exec resume …`) and it
shares the SIGTERM-then-SIGKILL pause/abandon contract with ClaudeRuntime.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tripwire.models.session import (
    AgentSession,
    RuntimeState,
    WorktreeEntry,
)
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes import CodexRuntime
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
        prompt="REVIEW THIS PR",
        system_append="",
        project_slug="test-proj",
        spawn_defaults=SpawnDefaults.model_validate(
            {
                "prompt_template": "{plan}",
                "resume_prompt_template": "resuming",
                "system_prompt_append": "",
                "invocation": {
                    "command": "codex",
                    "runtime": "codex",
                    "log_path_template": str(
                        tmp_path / "logs" / "{project_slug}" / "{session_id}.log"
                    ),
                    # disable the in-flight monitor for these unit tests; it
                    # has its own coverage and we don't want to mock its
                    # spawning side effects here.
                    "monitor": False,
                },
                "config": {
                    "model": "gpt-5-codex",
                    "effort": "medium",
                    "permission_mode": "bypassPermissions",
                    "provider": "codex",
                },
            }
        ),
        resume=resume,
    )


def test_validate_environment_passes_when_openai_api_key_present(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    CodexRuntime().validate_environment()


def test_validate_environment_passes_when_codex_auth_file_present(
    tmp_path, monkeypatch
):
    """Codex CLI also accepts `codex login` (writes ~/.codex/auth.json)
    instead of OPENAI_API_KEY. validate_environment must accept either."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_home = tmp_path
    monkeypatch.setenv("HOME", str(fake_home))
    auth = fake_home / ".codex" / "auth.json"
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}", encoding="utf-8")
    CodexRuntime().validate_environment()


def test_validate_environment_raises_when_no_auth(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    fake_home = tmp_path / "no-codex"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    with pytest.raises(RuntimeError, match=r"OPENAI_API_KEY|codex login"):
        CodexRuntime().validate_environment()


def test_start_invokes_popen_with_codex_exec_argv(tmp_path, monkeypatch):
    """First-spawn path: `codex exec --json -m MODEL -c model_reasoning_effort=…
    --sandbox … <PROMPT>` with the resolved cwd and start_new_session=True."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    prepped = _prepped(tmp_path)
    fake_proc = MagicMock()
    fake_proc.pid = 4242

    with patch(
        "tripwire.runtimes.codex._sp.Popen", return_value=fake_proc
    ) as mock_popen:
        result = CodexRuntime().start(prepped)

    mock_popen.assert_called_once()
    argv = mock_popen.call_args[0][0]
    assert argv[0] == "codex"
    assert "exec" in argv
    assert "--json" in argv
    assert "-m" in argv
    # model from spawn config threaded through
    assert "gpt-5-codex" in argv
    # reasoning effort comes through as a `-c model_reasoning_effort="medium"` pair
    assert any("model_reasoning_effort" in a and "medium" in a for a in argv)
    # sandbox: read-only is the default for codex (review-class workloads)
    assert "--sandbox" in argv
    assert "read-only" in argv
    # prompt is positional, last arg
    assert "REVIEW THIS PR" in argv

    kwargs = mock_popen.call_args[1]
    assert kwargs["cwd"] == str(prepped.code_worktree)
    assert kwargs["start_new_session"] is True

    # Result has the codex pid and a populated log_path
    assert result.pid == 4242
    log_path = Path(result.log_path)
    assert "test-proj" in str(log_path)
    assert log_path.parent.exists()


def test_start_with_resume_uses_exec_resume_subcommand(tmp_path, monkeypatch):
    """Resume path: `codex exec resume <SESSION_ID> [PROMPT]`. Note the
    spec said `--resume` but `codex --help` shows it's a subcommand."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    prepped = _prepped(tmp_path, resume=True)
    fake_proc = MagicMock()
    fake_proc.pid = 99

    with patch(
        "tripwire.runtimes.codex._sp.Popen", return_value=fake_proc
    ) as mock_popen:
        CodexRuntime().start(prepped)

    argv = mock_popen.call_args[0][0]
    assert argv[0] == "codex"
    # Subcommand chain: codex exec resume <SESSION_ID>
    assert argv[1] == "exec"
    assert "resume" in argv
    resume_idx = argv.index("resume")
    assert argv[resume_idx + 1] == "uuid-1"
    # On resume, --json is still set so the runtime can tail the stream
    assert "--json" in argv


def test_pause_sigterms_live_pid():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with (
        patch("tripwire.runtimes.codex.is_alive", side_effect=[True, False]),
        patch("tripwire.runtimes.codex.send_sigterm") as mock_sigterm,
        patch("tripwire.runtimes.codex.time.sleep"),
    ):
        CodexRuntime().pause(session)
    mock_sigterm.assert_called_once_with(999)


def test_pause_noop_on_dead_pid():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with (
        patch("tripwire.runtimes.codex.is_alive", return_value=False),
        patch("tripwire.runtimes.codex.send_sigterm") as mock_sigterm,
    ):
        CodexRuntime().pause(session)
    mock_sigterm.assert_not_called()


def test_status_reflects_is_alive():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with patch("tripwire.runtimes.codex.is_alive", return_value=True):
        assert CodexRuntime().status(session) == "running"
    with patch("tripwire.runtimes.codex.is_alive", return_value=False):
        assert CodexRuntime().status(session) == "exited"


def test_abandon_sigkills_stubborn_process():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(pid=999, claude_session_id="uuid-1"),
    )
    with (
        patch("tripwire.runtimes.codex.is_alive", return_value=True),
        patch("tripwire.runtimes.codex.send_sigterm"),
        patch("tripwire.runtimes.codex.time.sleep"),
        patch("os.kill") as mock_os_kill,
    ):
        CodexRuntime().abandon(session)
    import signal as _sig

    mock_os_kill.assert_called_once()
    assert mock_os_kill.call_args[0] == (999, _sig.SIGKILL)


def test_attach_command_returns_tail_f_on_log():
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(
            claude_session_id="uuid-1",
            log_path="/tmp/tripwire-logs/codex-s1.log",
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
    cmd = CodexRuntime().attach_command(session)
    assert isinstance(cmd, AttachExec)
    assert cmd.argv == ["tail", "-f", "/tmp/tripwire-logs/codex-s1.log"]


def test_attach_command_returns_instruction_when_no_log_path():
    session = AgentSession(id="s1", name="t", agent="a")
    cmd = CodexRuntime().attach_command(session)
    assert isinstance(cmd, AttachInstruction)


# Suppress unused-import warning for `os` (kept for documentation parity)
_ = os
