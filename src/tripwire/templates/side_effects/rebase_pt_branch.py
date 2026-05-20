"""side_effect: rebase_pt_branch.

Rebase the session's project-tracking (PT) worktree onto the base
branch. Wired into the ``executing → in_review`` route so the PR
opened against the project-tracking repo is up-to-date with main at
review time.

Looks up the PT worktree on the session by branch prefix
``proj/`` (the spawn-time convention). Skips quietly if the session
has no PT worktree (some legacy or container-only sessions).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="rebase_pt_branch")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument(
        "--upstream",
        default="origin/main",
        help="Branch to rebase onto. Defaults to origin/main.",
    )
    args = parser.parse_args()

    from tripwire.core.git_helpers import rebase_branch_onto
    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    runtime = getattr(session, "runtime_state", None)
    worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []
    pt_worktree = next(
        (wt for wt in worktrees if wt.branch.startswith("proj/")),
        None,
    )

    if pt_worktree is None:
        print(
            f"session {args.session_id}: no PT worktree (no branch starts with "
            f"'proj/'); skipping rebase",
            file=sys.stderr,
        )
        return 0

    wt_path = Path(pt_worktree.worktree_path).expanduser()
    if not wt_path.is_dir():
        print(
            f"session {args.session_id}: PT worktree path {wt_path} is missing; "
            f"skipping rebase (worktree may already be cleaned up)",
            file=sys.stderr,
        )
        return 0

    print(
        f"  rebasing {pt_worktree.branch} onto {args.upstream} at {wt_path}",
        file=sys.stderr,
    )
    try:
        rebase_branch_onto(wt_path, args.upstream)
    except Exception as exc:
        print(
            f"  REBASE FAILED: {exc}\n"
            f"  resolve conflicts in {wt_path} then retry the transition.",
            file=sys.stderr,
        )
        return 1

    print(f"  rebased {pt_worktree.branch} onto {args.upstream}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
