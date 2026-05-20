"""side_effect: flip_drafts_to_ready.

Mark every draft PR opened by the session as ready-for-review. Wired
into the ``verified → completed`` route. The session-complete CLI
historically called the underlying helper inline; under the v0.14.0
declarative model the executor invokes this script before the status
write.

Skips quietly when a worktree has no recorded ``draft_pr_url`` (legacy
sessions, container-only sessions).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="flip_drafts_to_ready")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    runtime = getattr(session, "runtime_state", None)
    worktrees = list(getattr(runtime, "worktrees", None) or []) if runtime else []

    flipped = 0
    failed: list[str] = []

    for wt in worktrees:
        pr_url = getattr(wt, "draft_pr_url", None)
        if not pr_url:
            continue
        print(f"  marking {pr_url} ready for review", file=sys.stderr)
        try:
            subprocess.run(
                ["gh", "pr", "ready", pr_url],
                check=True,
                capture_output=True,
                text=True,
                cwd=wt.worktree_path if Path(wt.worktree_path).is_dir() else None,
            )
            flipped += 1
        except subprocess.CalledProcessError as exc:
            stderr_text = (exc.stderr or "").strip() or str(exc)
            print(
                f"  FAILED to flip {pr_url}: {stderr_text}",
                file=sys.stderr,
            )
            failed.append(pr_url)
        except FileNotFoundError:
            print(
                "  FAILED: `gh` CLI not installed or not on PATH",
                file=sys.stderr,
            )
            return 1

    print(
        f"flipped {flipped} draft PR(s) to ready"
        + (f"; {len(failed)} failed" if failed else ""),
        file=sys.stderr,
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
