"""Tests for TmuxRuntime."""

from unittest.mock import patch

import pytest

from tripwire.models.session import (
    AgentSession,
    RuntimeState,
    WorktreeEntry,
)
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes.base import (
    AttachExec,
    AttachInstruction,
    PreppedSession,
)


def _prepped(tmp_path) -> PreppedSession:
    wt = WorktreeEntry(
        repo="SeidoAI/code",
        clone_path=str(tmp_path / "clone"),
        worktree_path=str(tmp_path / "wt"),
        branch="feat/s1",
    )
    (tmp_path / "wt").mkdir()
    return PreppedSession(
        session_id="s1",
        session=AgentSession(id="s1", name="test", agent="a"),
        project_dir=tmp_path,
        code_worktree=tmp_path / "wt",
        worktrees=[wt],
        claude_session_id="uuid-1",
        prompt="DO THE THING",
        system_append="",
        spawn_defaults=SpawnDefaults.model_validate({
            "prompt_template": "{plan}",
            "system_prompt_append": "",
        }),
    )


def test_validate_environment_missing_tmux_raises(monkeypatch):
    from tripwire.runtimes import TmuxRuntime

    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(Exception, match="tmux"):
        TmuxRuntime().validate_environment()


def test_validate_environment_with_tmux_present(fake_tmux_on_path):
    from tripwire.runtimes import TmuxRuntime

    TmuxRuntime().validate_environment()


def test_start_creates_tmux_session_and_sends_keys(
    fake_tmux_on_path, tmp_path
):
    from tripwire.runtimes import TmuxRuntime

    prepped = _prepped(tmp_path)
    fake_tmux_on_path.set_pane_text("Welcome to claude\n> ")

    result = TmuxRuntime().start(prepped)

    calls = fake_tmux_on_path.calls()
    commands = [c[0] for c in calls]
    assert "new-session" in commands
    assert "send-keys" in commands

    new_session = next(c for c in calls if c[0] == "new-session")
    assert "-s" in new_session
    session_name = new_session[new_session.index("-s") + 1]
    assert session_name.startswith("tw-s1")

    send_keys = next(c for c in calls if c[0] == "send-keys")
    assert "DO THE THING" in " ".join(send_keys)
    assert "Enter" in send_keys

    assert result.tmux_session_name == session_name
    assert result.claude_session_id == "uuid-1"


def test_start_timeout_when_ready_prompt_never_appears(
    fake_tmux_on_path, tmp_path
):
    from tripwire.runtimes import TmuxRuntime

    prepped = _prepped(tmp_path)
    fake_tmux_on_path.set_pane_text("still starting...")

    with patch("tripwire.runtimes.tmux._READY_POLL_INTERVAL", 0.01), \
         patch("tripwire.runtimes.tmux._READY_TIMEOUT", 0.05):
        with pytest.raises(Exception, match="did not reach ready prompt"):
            TmuxRuntime().start(prepped)

    calls = fake_tmux_on_path.calls()
    assert any(c[0] == "new-session" for c in calls)
    assert not any(c[0] == "send-keys" for c in calls)
