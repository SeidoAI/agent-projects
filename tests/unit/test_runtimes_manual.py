"""Tests for ManualRuntime."""

from pathlib import Path

from tripwire.models.session import (
    AgentSession,
    RuntimeState,
    WorktreeEntry,
)
from tripwire.models.spawn import SpawnDefaults
from tripwire.runtimes import ManualRuntime
from tripwire.runtimes.base import AttachInstruction, PreppedSession


def _prepped(tmp_path: Path) -> PreppedSession:
    wt = WorktreeEntry(
        repo="SeidoAI/code",
        clone_path=str(tmp_path / "clone"),
        worktree_path=str(tmp_path / "wt"),
        branch="feat/s1",
    )
    return PreppedSession(
        session_id="s1",
        session=AgentSession(id="s1", name="test", agent="a"),
        project_dir=tmp_path,
        code_worktree=tmp_path / "wt",
        worktrees=[wt],
        claude_session_id="uuid-1",
        prompt="do the thing",
        system_append="",
        project_slug="test-proj",
        spawn_defaults=SpawnDefaults(),
    )


def test_validate_environment_is_noop():
    ManualRuntime().validate_environment()


def test_start_prints_command_and_returns_state(tmp_path, capsys):
    runtime = ManualRuntime()
    prepped = _prepped(tmp_path)

    result = runtime.start(prepped)

    out = capsys.readouterr().out
    assert "claude --name s1 --session-id uuid-1" in out
    assert str(tmp_path / "wt") in out
    assert "kickoff.md" in out

    assert result.claude_session_id == "uuid-1"
    assert result.pid is None


def test_pause_is_noop_but_warns(capsys):
    session = AgentSession(id="s1", name="t", agent="a")
    ManualRuntime().pause(session)
    out = capsys.readouterr().out
    assert "manual" in out.lower()


def test_abandon_is_noop_but_warns(capsys):
    session = AgentSession(id="s1", name="t", agent="a")
    ManualRuntime().abandon(session)
    out = capsys.readouterr().out
    assert "manual" in out.lower()


def test_status_is_unknown():
    session = AgentSession(id="s1", name="t", agent="a")
    assert ManualRuntime().status(session) == "unknown"


def test_attach_command_returns_instruction(tmp_path):
    session = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(
            claude_session_id="uuid-1",
            worktrees=[
                WorktreeEntry(
                    repo="SeidoAI/code",
                    clone_path=str(tmp_path / "clone"),
                    worktree_path=str(tmp_path / "wt"),
                    branch="feat/s1",
                ),
            ],
        ),
    )
    cmd = ManualRuntime().attach_command(session)
    assert isinstance(cmd, AttachInstruction)
    assert "claude --name s1 --session-id uuid-1" in cmd.message
    assert "--resume" not in cmd.message
    assert str(tmp_path / "wt") in cmd.message


def test_attach_command_honours_resume_state(tmp_path):
    """When the last spawn was --resume, the attach instruction must
    include --resume (so the operator's paste matches what tripwire
    actually ran). Regression test for bug #3."""
    base_state = {
        "claude_session_id": "uuid-1",
        "worktrees": [
            WorktreeEntry(
                repo="SeidoAI/code",
                clone_path=str(tmp_path / "clone"),
                worktree_path=str(tmp_path / "wt"),
                branch="feat/s1",
            ),
        ],
    }
    resumed = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(**base_state, last_spawn_resumed=True),
    )
    fresh = AgentSession(
        id="s1",
        name="t",
        agent="a",
        runtime_state=RuntimeState(**base_state, last_spawn_resumed=False),
    )

    resumed_cmd = ManualRuntime().attach_command(resumed)
    fresh_cmd = ManualRuntime().attach_command(fresh)

    assert isinstance(resumed_cmd, AttachInstruction)
    assert isinstance(fresh_cmd, AttachInstruction)
    assert "--resume" in resumed_cmd.message
    assert "--resume" not in fresh_cmd.message
