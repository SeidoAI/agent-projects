"""SessionRuntime protocol and shared types.

Each runtime implementation (tmux, manual, future: container) owns
the lifecycle for one session: start, pause, abandon, status, attach.
The prep pipeline runs before ``start`` and is runtime-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from tripwire.models.session import AgentSession, WorktreeEntry
from tripwire.models.spawn import SpawnDefaults


@dataclass
class PreppedSession:
    """Output of the prep pipeline, consumed by a runtime's ``start``."""

    session_id: str
    session: AgentSession
    project_dir: Path
    code_worktree: Path
    worktrees: list[WorktreeEntry]
    claude_session_id: str
    prompt: str
    system_append: str
    project_slug: str
    spawn_defaults: SpawnDefaults
    resume: bool = False


@dataclass
class AttachExec:
    """Runtime wants `tripwire session attach` to execvp this argv."""

    argv: list[str]


@dataclass
class AttachInstruction:
    """Runtime has no process to attach to; print this message instead."""

    message: str


AttachCommand = AttachExec | AttachInstruction


RuntimeStatus = Literal["running", "exited", "unknown"]


@dataclass
class RuntimeStartResult:
    """What a runtime's ``start`` returns — fields the caller writes
    back onto ``session.runtime_state``."""

    claude_session_id: str
    worktrees: list[WorktreeEntry]
    started_at: str
    pid: int | None = None
    log_path: str | None = None


class SessionRuntime(Protocol):
    """Protocol for session execution runtimes."""

    name: str

    def validate_environment(self) -> None:
        """Raise with a user-facing message if this runtime can't run
        on this host (e.g. tmux missing). Called at prep time BEFORE
        any filesystem mutation."""
        ...

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        """Launch the agent process. Returns state to persist on
        ``session.runtime_state``."""
        ...

    def pause(self, session: AgentSession) -> None: ...
    def abandon(self, session: AgentSession) -> None: ...
    def status(self, session: AgentSession) -> RuntimeStatus: ...
    def attach_command(self, session: AgentSession) -> AttachCommand: ...
