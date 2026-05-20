"""side_effect: remove_worktrees.

Remove every worktree recorded on the session. Wired into abandon
routes and into ``verified → completed`` (clean up after a session
ships).

Lifts ``core.git_helpers.worktree_remove`` — the same helper the
existing CLIs use. Missing worktree dirs are no-ops.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="remove_worktrees")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--from-status", help="(unused — uniform executor interface)")
    parser.add_argument("--to-status", help="(unused — uniform executor interface)")
    args = parser.parse_args()

    from tripwire.core.git_helpers import worktree_remove
    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    runtime = getattr(session, "runtime_state", None)
    worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []

    removed = 0
    failed: list[str] = []

    for wt in worktrees:
        clone_path = Path(wt.clone_path).expanduser()
        wt_path = Path(wt.worktree_path).expanduser()
        if not wt_path.is_dir():
            print(
                f"  {wt.branch}: worktree dir already gone; skipping",
                file=sys.stderr,
            )
            continue
        if not clone_path.is_dir():
            print(
                f"  {wt.branch}: clone path {clone_path} missing; cannot remove "
                f"worktree {wt_path}",
                file=sys.stderr,
            )
            failed.append(wt.branch)
            continue
        try:
            worktree_remove(clone_path, wt_path)
            print(f"  removed worktree {wt_path}", file=sys.stderr)
            removed += 1
        except Exception as exc:
            print(
                f"  FAILED to remove worktree {wt_path}: {exc}",
                file=sys.stderr,
            )
            failed.append(wt.branch)

    print(
        f"removed {removed} worktree(s)"
        + (f"; {len(failed)} failed" if failed else ""),
        file=sys.stderr,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
