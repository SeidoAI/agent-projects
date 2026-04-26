"""Session runtime registry.

``RUNTIMES`` maps runtime name → ``SessionRuntime`` instance. Resolved
at spawn time from ``spawn_config.invocation.runtime``.
"""

from __future__ import annotations

from tripwire.runtimes.base import (
    AttachCommand,
    AttachExec,
    AttachInstruction,
    PreppedSession,
    RuntimeStartResult,
    RuntimeStatus,
    SessionRuntime,
)
from tripwire.runtimes.claude import ClaudeRuntime
from tripwire.runtimes.codex import CodexRuntime
from tripwire.runtimes.manual import ManualRuntime

RUNTIMES: dict[str, SessionRuntime] = {
    "claude": ClaudeRuntime(),
    "codex": CodexRuntime(),
    "manual": ManualRuntime(),
}


def get_runtime(name: str) -> SessionRuntime:
    """Look up a runtime by name. Raises ValueError on unknown names
    with the valid options in the message."""
    if name not in RUNTIMES:
        valid = ", ".join(sorted(RUNTIMES))
        raise ValueError(f"Unknown runtime '{name}'. Valid runtimes: {valid}")
    return RUNTIMES[name]


__all__ = [
    "RUNTIMES",
    "AttachCommand",
    "AttachExec",
    "AttachInstruction",
    "ClaudeRuntime",
    "CodexRuntime",
    "ManualRuntime",
    "PreppedSession",
    "RuntimeStartResult",
    "RuntimeStatus",
    "SessionRuntime",
    "get_runtime",
]
