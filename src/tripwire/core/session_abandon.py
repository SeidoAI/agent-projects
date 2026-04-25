"""Session abandon orchestration (v0.7.9 §A4).

`abandoned` is the terminal status that does NOT claim success. It's
the answer to "this session can't legitimately reach `done`, but I
need to stop pretending it's still in flight." The framework's two
terminal states are `done` (passed every gate) and `abandoned`
(stopped, didn't pass). There is no third "done with caveats" state
on purpose — that's what spec §A4 is rejecting.

Behaviour:
- Kill the runtime handle if the session is still executing.
- Close any OPEN PRs for the session's branches via ``gh pr close``.
  Merged PRs are left alone (closing a merged PR makes no sense).
- Remove every worktree the session created.
- Transition the session to ``abandoned``.
- Issues are NOT closed as ``done``. They stay where they are; the
  PM moves them to ``backlog`` / ``canceled`` / ``won't-do`` per case.

The runtime tear-down is best-effort. If any step fails, we record
the failure in the result and proceed with the rest — abandoning is
about state cleanup, and a failure in one step shouldn't block the
others. The session ALWAYS transitions to ``abandoned``; that's the
contract.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.git_helpers import worktree_remove
from tripwire.core.session_store import load_session, save_session


class AbandonError(ValueError):
    """Raised when abandon refuses to proceed (e.g. already terminal)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class AbandonResult:
    session_id: str
    prs_closed: list[int] = field(default_factory=list)
    prs_skipped_merged: list[int] = field(default_factory=list)
    worktrees_removed: list[str] = field(default_factory=list)
    runtime_killed: bool = False
    errors: list[str] = field(default_factory=list)


def abandon_session(
    project_dir: Path,
    session_id: str,
) -> AbandonResult:
    """Tear down a session and transition it to ``abandoned``.

    Refuses if the session is already terminal (``done`` or
    ``abandoned``) — there's nothing to do, and continuing would risk
    masking a state-machine bug. Otherwise: kill runtime → close open
    PRs → remove worktrees → transition. Each step's failure is
    recorded but doesn't block the others.
    """
    session = load_session(project_dir, session_id)
    result = AbandonResult(session_id=session_id)

    # `completed` is a legacy terminal that predates the v0.7.9 split
    # of done vs abandoned. We refuse it for the same reason as `done`:
    # the session has already concluded and re-abandoning it would
    # paper over a state-machine bug rather than fix it.
    if session.status in ("done", "abandoned", "completed"):
        raise AbandonError(
            "abandon/already_terminal",
            f"Session {session_id!r} is already {session.status!r}; "
            "abandon would be a no-op.",
        )

    # 1. Kill runtime handle if the session is still live. We don't
    #    require a live process — `paused`/`failed` sessions can also
    #    be abandoned and the runtime tear-down is a no-op for them.
    if session.status == "executing":
        try:
            from tripwire.core.spawn_config import load_resolved_spawn_config
            from tripwire.runtimes import get_runtime

            spawn = load_resolved_spawn_config(project_dir, session=session)
            runtime = get_runtime(spawn.invocation.runtime)
            runtime.abandon(session)
            result.runtime_killed = True
        except (RuntimeError, ValueError, FileNotFoundError) as exc:
            result.errors.append(f"runtime tear-down failed: {exc}")

    # 2. Close any open PRs for the session's branches. Merged PRs
    #    stay merged — closing them is meaningless. Per worktree:
    #    - If the worktree carries a v0.7.5 ``draft_pr_url``, close
    #      that URL directly. Faster than `gh pr list` + `pr close
    #      <number>`, and matches the v0.7.5 contract for orphan
    #      drafts on session-start.
    #    - Otherwise, find any open PR via `gh pr list --head` and
    #      close it. This covers non-draft PRs and v0.7.4 dual-PR
    #      worktrees that came up before draft_pr_url existed.
    for wt in session.runtime_state.worktrees:
        if wt.draft_pr_url:
            verdict = _close_pr_by_url(wt.draft_pr_url, wt.worktree_path)
        else:
            verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)
        if verdict.error:
            result.errors.append(verdict.error)
        if verdict.merged_pr is not None:
            result.prs_skipped_merged.append(verdict.merged_pr)
        if verdict.closed_pr is not None:
            result.prs_closed.append(verdict.closed_pr)

    # 3. Remove worktrees. Best-effort — a missing clone path or
    #    already-removed worktree shouldn't block the status flip.
    for wt in session.runtime_state.worktrees:
        wt_path = Path(wt.worktree_path)
        if not wt_path.exists():
            continue
        try:
            worktree_remove(Path(wt.clone_path), wt_path)
            result.worktrees_removed.append(wt.worktree_path)
        except (subprocess.SubprocessError, OSError) as exc:
            result.errors.append(f"worktree remove failed for {wt_path}: {exc}")

    # 4. Transition. This step always happens — it's the contract.
    now = datetime.now(tz=timezone.utc)
    session.status = "abandoned"
    session.updated_at = now
    if session.engagements:
        last = session.engagements[-1]
        if last.ended_at is None:
            last.ended_at = now
            last.outcome = "abandoned"
    save_session(project_dir, session)

    return result


@dataclass
class _PrCloseVerdict:
    closed_pr: int | None = None
    merged_pr: int | None = None
    error: str | None = None


def _close_pr_by_url(pr_url: str, worktree_path: str) -> _PrCloseVerdict:
    """Close a PR by its URL (the v0.7.5 fast path).

    Used when the worktree carries a ``draft_pr_url`` from prep. Skips
    the `gh pr list` round trip. The PR number is parsed from the URL
    tail purely so the caller's per-step accounting (``prs_closed``)
    stays integer-typed; if the URL doesn't end in ``/<digits>``, we
    fall back to recording -1.
    """
    verdict = _PrCloseVerdict()
    try:
        close = subprocess.run(
            ["gh", "pr", "close", pr_url],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=worktree_path,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        verdict.error = f"gh pr close {pr_url} failed: {exc}"
        return verdict

    if close.returncode != 0:
        verdict.error = (
            f"gh pr close {pr_url} exit={close.returncode}: "
            f"{(close.stderr or '').strip()}"
        )
        return verdict

    tail = pr_url.rsplit("/", 1)[-1]
    verdict.closed_pr = int(tail) if tail.isdigit() else -1
    return verdict


def _close_pr_for_branch(branch: str, worktree_path: str) -> _PrCloseVerdict:
    """Close any open PR whose head is ``branch``. Skip merged PRs.

    Run ``gh`` from inside ``worktree_path`` so it picks up the right
    remote when worktrees come from different origins (the v0.7.4
    dual-PR case).
    """
    verdict = _PrCloseVerdict()
    try:
        listing = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number,state",
                "--limit",
                "5",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=worktree_path,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        verdict.error = f"gh pr list failed for {branch}: {exc}"
        return verdict

    if listing.returncode != 0:
        verdict.error = (
            f"gh pr list for {branch} exit={listing.returncode}: "
            f"{(listing.stderr or '').strip()}"
        )
        return verdict

    try:
        prs = json.loads(listing.stdout or "[]")
    except json.JSONDecodeError as exc:
        verdict.error = f"gh pr list returned invalid JSON for {branch}: {exc}"
        return verdict

    for pr in prs:
        number = pr.get("number")
        state = (pr.get("state") or "").upper()
        if not isinstance(number, int):
            continue
        if state == "MERGED":
            verdict.merged_pr = number
            continue
        if state != "OPEN":
            continue
        try:
            close = subprocess.run(
                [
                    "gh",
                    "pr",
                    "close",
                    str(number),
                    "--comment",
                    "Session abandoned (`tripwire session abandon`).",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                cwd=worktree_path,
            )
            if close.returncode == 0:
                verdict.closed_pr = number
            else:
                verdict.error = (
                    f"gh pr close #{number} exit={close.returncode}: "
                    f"{(close.stderr or '').strip()}"
                )
        except (subprocess.SubprocessError, OSError) as exc:
            verdict.error = f"gh pr close #{number} failed: {exc}"
        # Closing the first open PR per branch is enough; gh shouldn't
        # show two open PRs for the same head, but if it does the
        # leftover surfaces in the next abandon run.
        break

    return verdict
