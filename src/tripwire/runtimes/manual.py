"""ManualRuntime — prep-only runtime.

Does the skill copy + CLAUDE.md render like the subprocess runtime,
then prints the exact claude invocation the operator should run,
and exits. The operator launches claude themselves from the code
worktree.

Pause/abandon are no-ops (tripwire has no process handle); status is
always 'unknown'. Attach prints the same instruction as start.
"""

from __future__ import annotations

from datetime import datetime, timezone

import click

from tripwire.models.session import AgentSession
from tripwire.runtimes.base import (
    AttachCommand,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
)


def _start_command(
    worktree: str,
    session_id: str,
    claude_session_id: str,
    *,
    resume: bool = False,
) -> str:
    resume_flag = " --resume" if resume else ""
    return (
        f"cd {worktree}\n"
        f"  claude --name {session_id} --session-id {claude_session_id}"
        f"{resume_flag}"
    )


class ManualRuntime:
    name = "manual"

    def validate_environment(self) -> None:
        return

    def start(self, prepped: PreppedSession) -> RuntimeStartResult:
        click.echo("Prepared — manual runtime. To launch, run:")
        click.echo("")
        click.echo(
            "  " + _start_command(
                str(prepped.code_worktree),
                prepped.session_id,
                prepped.claude_session_id,
                resume=prepped.resume,
            )
        )
        click.echo("")
        click.echo(
            f"Kickoff prompt: {prepped.code_worktree}/.tripwire/kickoff.md "
            "(also loaded into claude on first turn via CLAUDE.md)."
        )
        return RuntimeStartResult(
            claude_session_id=prepped.claude_session_id,
            worktrees=prepped.worktrees,
            started_at=datetime.now(tz=timezone.utc).isoformat(),
        )

    def pause(self, session: AgentSession) -> None:
        click.echo(
            f"Session '{session.id}' is on the manual runtime — no process to pause. "
            "Interrupt claude yourself in the terminal where you launched it."
        )

    def abandon(self, session: AgentSession) -> None:
        click.echo(
            f"Session '{session.id}' is on the manual runtime — no process to abandon. "
            "Close the claude terminal yourself."
        )

    def status(self, session: AgentSession) -> RuntimeStatus:
        return "unknown"

    def attach_command(self, session: AgentSession) -> AttachCommand:
        state = session.runtime_state
        if not state.worktrees or not state.claude_session_id:
            return AttachInstruction(
                message=(
                    f"Session '{session.id}' has no recorded worktree or "
                    "claude session id. Re-run 'tripwire session spawn'."
                )
            )
        wt = state.worktrees[0].worktree_path
        return AttachInstruction(
            message=(
                "This session is on the manual runtime — launch it yourself:\n\n"
                f"  {_start_command(wt, session.id, state.claude_session_id, resume=state.last_spawn_resumed)}\n"
            )
        )
