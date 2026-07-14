"""Post-write hook: reset session ack markers when the route opts in."""

from __future__ import annotations

from pathlib import Path

from tripwire.models.session import AgentSession


def reset_acks_if_requested(
    project_dir: Path, *, session: AgentSession, flags: dict
) -> int:
    """Reset session ack markers when ``flags['reset_acks']`` is True.
    Returns the number of acks deleted. Used by the reopen route."""
    if not flags.get("reset_acks", False):
        return 0
    try:
        from tripwire.core.session_reopen import _reset_session_acks
    except ImportError:
        return 0
    reason = flags.get("reason", "session reopened")
    return _reset_session_acks(project_dir, session.id, reason)
