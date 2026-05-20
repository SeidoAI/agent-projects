"""side_effect: kill_runtime.

SIGTERM the session's runtime process. Wired into abandon routes so
an in-flight agent is stopped before its worktrees are torn down.

Reads ``session.runtime_state.pid``. No-op (exit 0) when the PID is
unset, the process has already exited, or the PID is owned by
someone else (defensive: don't kill arbitrary processes).
"""

from __future__ import annotations

import argparse
import errno
import os
import signal
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="kill_runtime")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    runtime = getattr(session, "runtime_state", None)
    pid = getattr(runtime, "pid", None) if runtime else None

    if pid is None:
        print(
            f"session {args.session_id}: no runtime pid recorded; nothing to kill",
            file=sys.stderr,
        )
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(
            f"  pid {pid} already exited; nothing to kill",
            file=sys.stderr,
        )
        return 0
    except PermissionError:
        print(
            f"  pid {pid} owned by another user; refusing to kill",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return 0
        print(f"  os.kill({pid}, SIGTERM) failed: {exc}", file=sys.stderr)
        return 1

    print(f"  SIGTERM sent to pid {pid}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
