"""side_effect: close_open_prs.

Close every open PR opened by the session. Wired into abandon routes.

Lifts ``core.session_abandon._close_pr_for_branch`` /
``_close_pr_by_url`` — the same logic the abandon CLI uses today
(see ``session_abandon.py`` lines 109-119). Each PR is closed via
``gh pr close``; already-merged PRs are skipped without error;
already-closed PRs are no-ops.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="close_open_prs")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--from-status", help="(unused — uniform executor interface)")
    parser.add_argument("--to-status", help="(unused — uniform executor interface)")
    args = parser.parse_args()

    from tripwire.core.session_abandon import (
        _close_pr_by_url,
        _close_pr_for_branch,
    )
    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    runtime = getattr(session, "runtime_state", None)
    worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []

    closed = 0
    skipped_merged = 0
    errors: list[str] = []

    for wt in worktrees:
        wt_path = Path(wt.worktree_path).expanduser()
        if not wt_path.is_dir():
            # Worktree dir already gone — gh has no cwd to operate from.
            # Treat as already-handled.
            continue

        # Prefer the fast path when the worktree carries a draft_pr_url
        # (mirrors session_abandon.py:109-113).
        if wt.draft_pr_url:
            verdict = _close_pr_by_url(wt.draft_pr_url, wt.worktree_path)
        else:
            verdict = _close_pr_for_branch(wt.branch, wt.worktree_path)

        if verdict.merged_pr is not None:
            print(
                f"  {wt.branch}: PR #{verdict.merged_pr} already merged; leaving as-is",
                file=sys.stderr,
            )
            skipped_merged += 1
        if verdict.closed_pr is not None:
            print(
                f"  {wt.branch}: closed PR #{verdict.closed_pr}",
                file=sys.stderr,
            )
            closed += 1
        if verdict.error:
            print(
                f"  FAILED to close PR for {wt.branch}: {verdict.error}",
                file=sys.stderr,
            )
            errors.append(wt.branch)

    summary = f"closed {closed} PR(s)"
    if skipped_merged:
        summary += f"; {skipped_merged} already merged (skipped)"
    if errors:
        summary += f"; {len(errors)} failed"
    print(summary, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
