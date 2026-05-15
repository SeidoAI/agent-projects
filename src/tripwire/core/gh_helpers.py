"""Centralised ``gh`` (GitHub CLI) subprocess plumbing.

Before this module landed, seven-plus call sites across validators,
lifecycle helpers, and CLI commands each open-coded the same
``subprocess.run(["gh", ...], capture_output=True, ...)`` invocation
plus JSON parsing. The duplication made it easy for the timeout, the
``check=False`` semantics, the ``cwd=`` plumbing, and the
``FileNotFoundError`` (``gh`` not installed) handling to drift
per-callsite.

This module is the single place ``gh`` is invoked. Every public helper:

- Calls ``gh`` with a fixed timeout via :func:`_run_gh`.
- Wraps subprocess / OS errors into :class:`GhError` so callers can
  catch one exception type rather than the open set
  (``subprocess.SubprocessError``, ``OSError``, ``json.JSONDecodeError``).
- Returns a normalised result shape (a ``dict`` from ``--json``, or
  ``None`` for "no match", or ``None`` for fire-and-forget commands).

Callers preserve their existing fail-quiet vs fail-loud contract by
choosing whether to catch :class:`GhError`. The helpers do not silently
swallow failures themselves — that decision stays with the caller, who
knows whether a missing ``gh`` should block a transition or just warn.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

__all__ = [
    "GhError",
    "get_merged_pr_for_branch",
    "gh_pr_close",
    "gh_pr_ready",
]


# Default timeout for every gh subprocess call. Matches the previous
# per-callsite timeouts (10s for list/read operations, 15s for write
# operations). The longer of the two is used here — callers that want
# tighter bounds can wrap their own ``GhError`` handling around a
# shorter ``signal.alarm``-style guard.
_DEFAULT_TIMEOUT = 15


class GhError(RuntimeError):
    """Raised for any ``gh`` subprocess failure.

    Covers three classes of failure that callers previously had to
    catch individually:

    - ``gh`` exited non-zero (``returncode != 0``)
    - ``gh`` is not installed (``FileNotFoundError`` from ``subprocess.run``)
    - ``gh`` raised a ``subprocess.SubprocessError`` (timeout, etc.)

    The message is always prefixed with the failing command so logs
    point at the offending invocation without the caller having to
    reconstruct it.
    """


def _run_gh(
    args: list[str], *, cwd: Path | str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run ``gh <args>`` and return the completed process.

    ``check=False`` — a non-zero exit is converted into :class:`GhError`
    here rather than surfaced as ``CalledProcessError``. Same for
    ``FileNotFoundError`` ("gh not installed") and other subprocess
    errors. Callers see exactly one exception type for every gh failure.

    ``cwd`` is forwarded as ``str(cwd)`` when supplied so the worktree-
    scoped callers (where the right remote depends on the directory)
    keep their existing behaviour.
    """
    cmd = ["gh", *args]
    try:
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=_DEFAULT_TIMEOUT,
            cwd=str(cwd) if cwd is not None else None,
        )
    except FileNotFoundError as exc:
        # ``gh`` not installed. Surface a clear actionable message rather
        # than the bare ``FileNotFoundError`` callers used to bury.
        raise GhError(
            f"gh not installed (cannot run {' '.join(cmd)!r}): {exc}"
        ) from exc
    except subprocess.SubprocessError as exc:
        # Timeouts, OS-level signal interruptions, etc.
        raise GhError(f"gh subprocess failed for {' '.join(cmd)!r}: {exc}") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "<no stderr>"
        raise GhError(f"gh {' '.join(args)} exit={result.returncode}: {stderr}")
    return result


def get_merged_pr_for_branch(
    branch: str, *, cwd: Path | str | None = None
) -> dict | None:
    """Return the merged PR's JSON dict for ``branch``, or ``None``.

    Calls ``gh pr list --head <branch> --state merged --json
    number,mergedAt,state,mergeCommit,headRefName --limit 1`` and
    returns the first entry or ``None`` if the array is empty.

    ``cwd`` should be the worktree path when multiple worktrees on the
    same session can point at different origins — ``gh`` picks up the
    right remote from the directory it runs in.

    Raises :class:`GhError` on subprocess / network failure or invalid
    JSON. Callers that want the old fail-quiet behaviour wrap the call
    in ``try: ... except GhError: return None``.
    """
    result = _run_gh(
        [
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "merged",
            "--json",
            "number,mergedAt,state,mergeCommit,headRefName",
            "--limit",
            "1",
        ],
        cwd=cwd,
    )
    stdout = (result.stdout or "").strip()
    if not stdout:
        return None
    try:
        prs = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise GhError(
            f"gh pr list returned invalid JSON for branch {branch!r}: {exc}"
        ) from exc
    if not isinstance(prs, list) or not prs:
        return None
    first = prs[0]
    if not isinstance(first, dict):
        return None
    return first


def gh_pr_ready(
    target: str | int, *, undo: bool = False, cwd: Path | str | None = None
) -> None:
    """Flip a PR to ready-for-review (or back to draft with ``undo=True``).

    ``target`` is the PR number or URL — gh accepts both. With
    ``undo=True``, runs ``gh pr ready <target> --undo`` to flip a PR
    back to draft.

    Raises :class:`GhError` on failure. Caller decides whether to
    swallow the error (best-effort sweeps) or surface it (operator-
    invoked Layer-1 commands).
    """
    args = ["pr", "ready", str(target)]
    if undo:
        args.append("--undo")
    _run_gh(args, cwd=cwd)


def gh_pr_close(
    target: str | int,
    *,
    comment: str | None = None,
    cwd: Path | str | None = None,
) -> None:
    """Close a PR via ``gh pr close <target>``.

    ``target`` is the PR number or URL. Pass ``comment=...`` to attach
    a close comment (used by ``session abandon`` to record why the PR
    was closed).

    Raises :class:`GhError` on failure.
    """
    args = ["pr", "close", str(target)]
    if comment is not None:
        args.extend(["--comment", comment])
    _run_gh(args, cwd=cwd)
