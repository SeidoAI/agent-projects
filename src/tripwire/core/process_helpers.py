"""Process helper functions for session lifecycle management."""

from __future__ import annotations

import os
import signal


def is_alive(pid: int) -> bool:
    """Check whether a process with the given PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def send_sigterm(pid: int) -> bool:
    """Send SIGTERM to a process. Returns True if the process existed."""
    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except ProcessLookupError:
        return False
