"""side_effect: sweep_issues_forward.

Drive every member issue of *session-id* forward to match the session's
current state. Lifts ``core.status_contract.sweep_issues`` — the same
in-process helper that the ``tripwire session sweep-issues-forward``
CLI uses.

Wired into routes that flip the session into a state where member
issues should track along (planned→queued, executing→in_review,
review-approved, verified→completed). The executor invokes this
script after validators pass and before the status write; any
non-zero exit aborts the transition.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(prog="sweep_issues_forward")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()

    from tripwire.core.status_contract import sweep_issues, sweep_target_for
    from tripwire.core.store import load_session

    project_dir = args.project_dir.expanduser().resolve()
    session = load_session(project_dir, args.session_id)

    target = sweep_target_for(session.status.value)
    if target is None:
        print(
            f"session {args.session_id}: status {session.status.value!r} has no "
            f"sweep target; nothing to do",
            file=sys.stderr,
        )
        return 0

    if not session.issues:
        print(
            f"session {args.session_id}: no member issues; nothing to sweep",
            file=sys.stderr,
        )
        return 0

    sweep = sweep_issues(project_dir, session, session.status.value)
    for key in sweep.changed:
        print(f"  advanced {key} → {target}", file=sys.stderr)
    for p in sweep.partial:
        print(
            f"  PARTIAL {p.issue_key}: {p.started_at_status} → "
            f"{p.reached_status} (failed {p.failed_at_step}: {p.reason})",
            file=sys.stderr,
        )

    print(
        f"swept {len(sweep.changed)} of {len(session.issues)} issue(s) → {target}"
        + (f"; {len(sweep.partial)} stuck mid-lifecycle" if sweep.partial else ""),
        file=sys.stderr,
    )

    # Partial sweeps are half-broken state — abort the transition so the
    # operator addresses the stuck issues before retrying.
    return 1 if sweep.partial else 0


if __name__ == "__main__":
    sys.exit(main())
