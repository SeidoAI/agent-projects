"""Process helper functions for session lifecycle management."""

from __future__ import annotations

import os
import signal


def is_alive(pid: int) -> bool:
    """Check whether a process with the given PID is alive.

    Zombies count as dead: a terminated-but-unreaped child still
    exists in the process table, so ``os.kill(pid, 0)`` succeeds —
    but the process is no longer doing any work. We opportunistically
    ``waitpid(WNOHANG)`` to reap it if it's our own child. If the pid
    isn't ours (the typical case for cross-invocation CLI checks),
    ``waitpid`` raises ``ChildProcessError`` and we fall through: the
    zombie will be reaped by init (or whoever is the real parent).
    """
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:
        reaped, _ = os.waitpid(pid, os.WNOHANG)
        if reaped == pid:
            return False
    except (ChildProcessError, OSError):
        pass
    return True


def send_sigterm(pid: int) -> bool:
    """Send SIGTERM to a process. Returns True if the process existed."""
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
