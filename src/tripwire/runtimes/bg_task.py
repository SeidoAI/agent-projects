"""Background-task helper — run a subprocess to completion, capturing
the full stdout/stderr stream reliably.

Background
==========

Earlier iterations of this helper streamed output one line at a time
via ``Popen.stdout.readline()`` in a polling loop, then called
``proc.wait()`` separately. That pattern has a race window: if the
subprocess writes its output and exits between the last ``readline()``
returning empty-string and the ``wait()`` call, the buffered output
that was already in the pipe (but not yet drained) is discarded when
Python closes the pipe on the wait path. The symptom — observed by
PM-handoff #6 — was 0-byte captures for subprocesses that *did* write
to stdout, masking failures with an empty log.

The fix is structural: use ``subprocess.communicate(timeout=...)``,
which drains both pipes to EOF and then waits in one atomic step. No
manual readline loop, no race.

This helper is intentionally narrow: it runs one command, waits for it
to finish (or kills it on timeout), and returns ``(returncode, stdout,
stderr)``. Anything wanting fancier semantics (long-running tail,
streaming progress) should use a different mechanism — that's the
streaming-and-poll path this module is replacing.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BgTaskResult:
    """Outcome of :func:`run_bg_task`.

    ``stdout`` and ``stderr`` are decoded text; ``returncode`` is the
    OS exit status (or ``-1`` when the child was killed on timeout).
    ``timed_out`` is True iff we killed the child for exceeding the
    deadline — callers that care about partial output should still
    consult ``stdout``/``stderr`` (``communicate`` drains both pipes
    before re-raising :class:`subprocess.TimeoutExpired`).
    """

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


def run_bg_task(
    argv: list[str],
    *,
    cwd: Path | str | None = None,
    timeout: float | None = 60.0,
    env: dict[str, str] | None = None,
) -> BgTaskResult:
    """Spawn ``argv`` as a subprocess and return its captured output.

    The implementation uses ``subprocess.Popen(..., stdout=PIPE,
    stderr=PIPE)`` + ``communicate(timeout=...)`` so all output the
    child wrote to stdout/stderr is captured atomically. No streaming-
    and-poll race — the contract is "after this function returns,
    ``result.stdout`` is exactly what the child wrote to stdout."

    On timeout, the child is killed and any partial output captured so
    far is returned with ``timed_out=True`` and ``returncode=-1``.
    """
    cwd_str = str(cwd) if cwd is not None else None
    proc = subprocess.Popen(
        argv,
        cwd=cwd_str,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Kill + drain. communicate() after kill() is safe and gives us
        # whatever was buffered before SIGKILL.
        proc.kill()
        try:
            out, err = proc.communicate(timeout=5.0)
        except subprocess.TimeoutExpired:
            out = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            err = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return BgTaskResult(returncode=-1, stdout=out or "", stderr=err or "", timed_out=True)

    return BgTaskResult(
        returncode=proc.returncode,
        stdout=out or "",
        stderr=err or "",
        timed_out=False,
    )
