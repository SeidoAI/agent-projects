"""Project-wide file locking primitives.

`project_lock` is a context manager that acquires an exclusive `fcntl.flock`
on a lock file inside the project directory. Used by:

- `tripwire.core.key_allocator` to atomically increment issue/session counters
- `tripwire.core.validator.apply_fixes` to serialise concurrent --fix calls

The polling loop with `LOCK_EX | LOCK_NB` exists because we need a timeout
(blocking flock has none). Acquisition is short — read a number, increment,
write back — so the polling overhead is negligible.

Stale-lock handling: `fcntl.flock` is an advisory lock held by the file
descriptor, and it is automatically released when the holding process
exits (even if the process crashes without unlocking). Stale *files* are
cosmetic only — they don't block acquisition. The soft staleness check
here exists to emit a warning when a lock file's mtime is older than
`STALE_LOCK_AGE_S`, which hints that a previous process left without
cleaning up (normal behaviour, but worth logging).

Unix-only (uses `fcntl`). Windows is not currently supported.
"""

from __future__ import annotations

import fcntl
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from tripwire.core import paths

logger = logging.getLogger(__name__)

DEFAULT_LOCK_TIMEOUT_S = 10.0
LOCK_POLL_INTERVAL_S = 0.05
STALE_LOCK_AGE_S = 60.0


class LockTimeout(TimeoutError):
    """Raised when a lock cannot be acquired within the timeout."""


@contextmanager
def project_lock(
    project_dir: Path,
    *,
    name: str = paths.PROJECT_LOCK,
    timeout_s: float = DEFAULT_LOCK_TIMEOUT_S,
) -> Iterator[None]:
    """Acquire an exclusive `flock` on `<project_dir>/<name>`.

    Polls with a tight loop because `flock(LOCK_EX | LOCK_NB)` returns
    immediately and we need a timeout. The lock file is created on first
    use and persisted (it stays in the project repo, gitignored).

    If the lock file already exists and its mtime is older than
    `STALE_LOCK_AGE_S`, logs a warning noting that a previous process
    likely exited without touching the lock file. The OS has already
    released the advisory `flock` — this is just observability.

    Raises:
        LockTimeout: if the lock cannot be acquired within `timeout_s`.
    """
    lock_path = project_dir / name
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    if lock_path.exists():
        try:
            age = time.time() - lock_path.stat().st_mtime
        except OSError:
            age = 0.0
        if age > STALE_LOCK_AGE_S:
            logger.warning(
                "Lock file %s is %.0fs old — previous tripwire process likely "
                "exited without touching it (advisory lock is released on "
                "process exit; proceeding).",
                lock_path,
                age,
            )

    lock_path.touch(exist_ok=True)

    deadline = time.monotonic() + timeout_s
    with lock_path.open("a") as fh:
        while True:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise LockTimeout(
                        f"Could not acquire lock {lock_path} within "
                        f"{timeout_s}s. Another tripwire process may be "
                        f"holding it."
                    ) from None
                time.sleep(LOCK_POLL_INTERVAL_S)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
