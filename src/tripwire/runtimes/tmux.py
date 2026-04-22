"""TmuxRuntime — manages an interactive claude inside a tmux session.

Uses tmux for the live-attach story. Launches
``claude --name <slug> --session-id <uuid>`` (no ``-p``) inside
``tmux new-session -d -s tw-<id>``, polls for claude's ready prompt
via ``tmux capture-pane``, then delivers the kickoff prompt with
``tmux send-keys``.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime, timezone

import click

from tripwire.core.spawn_config import build_claude_args
from tripwire.models.session import AgentSession
from tripwire.runtimes.base import (
    AttachCommand,
    AttachExec,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
)

_READY_MARKER = "> "
_READY_POLL_INTERVAL = 0.25
_READY_TIMEOUT = 10.0


def _tmux_session_name(session_id: str) -> str:
    return f"tw-{session_id}"


def _wait_for_ready(session_name: str) -> None:
    """Poll `tmux capture-pane` until claude's ready prompt appears.
    Raises RuntimeError on timeout."""
    deadline = time.monotonic() + _READY_TIMEOUT
    while time.monotonic() < deadline:
        try:
            out = subprocess.run(
                ["tmux", "capture-pane", "-pt", session_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
        except subprocess.SubprocessError:
            out = None
        if out is not None and _READY_MARKER in out.stdout:
            return
        time.sleep(_READY_POLL_INTERVAL)
    raise RuntimeError(
        "claude did not reach ready prompt within "
        f"{int(_READY_TIMEOUT)}s. tmux session is still running — "
        "attach with 'tripwire session attach <id>' and paste the "
        "prompt from <code-worktree>/.tripwire/kickoff.md."
    )


class TmuxRuntime:
    name = "tmux"

    def validate_environment(self) -> None:
        if shutil.which("tmux") is None:
            raise click.ClickException(
                "tmux runtime requires tmux on PATH. "
                "Install tmux or set spawn_config.invocation.runtime: manual."
            )

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        session_name = _tmux_session_name(prepped.session_id)
        claude_args = build_claude_args(
            prepped.spawn_defaults,
            prompt=None,
            interactive=True,
            system_append=prepped.system_append,
            session_id=prepped.session_id,
            claude_session_id=prepped.claude_session_id,
        )

        subprocess.run(
            [
                "tmux", "new-session", "-d",
                "-s", session_name,
                "-c", str(prepped.code_worktree),
                "--",
                *claude_args,
            ],
            check=True,
        )

        _wait_for_ready(session_name)

        subprocess.run(
            [
                "tmux", "send-keys", "-t", session_name,
                prepped.prompt, "Enter",
            ],
            check=True,
        )

        return RuntimeStartResult(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
            tmux_session_name=session_name,
        )

    # Lifecycle methods filled in T11
    def pause(self, session: AgentSession) -> None:
        raise NotImplementedError

    def abandon(self, session: AgentSession) -> None:
        raise NotImplementedError

    def status(self, session: AgentSession) -> RuntimeStatus:
        raise NotImplementedError

    def attach_command(self, session: AgentSession) -> AttachCommand:
        raise NotImplementedError
