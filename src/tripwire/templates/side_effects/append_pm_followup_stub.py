"""side_effect: append_pm_followup_stub.

Append a ``## PM follow-up`` section to the session's plan.md so a
resumed agent has a designated place to read PM-supplied follow-up
findings. Wired into the ``completed → paused`` reopen route.

Idempotent: if the section already exists, no-op (exit 0). The PM
fills the section between reopen and re-spawn.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_STUB_HEADING = "## PM follow-up"

_STUB_BODY_TEMPLATE = """\

{heading}

_Reopened {timestamp}. Address the findings below before resuming
implementation. Replace this stub with the PM's specific bullets;
each bullet is one finding (severity, suggested fix, file:line)._

- [ ] (placeholder — PM fills in)

"""


def main() -> int:
    parser = argparse.ArgumentParser(prog="append_pm_followup_stub")
    parser.add_argument("--project-dir", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--from-status", help="(unused — uniform executor interface)")
    parser.add_argument("--to-status", help="(unused — uniform executor interface)")
    args = parser.parse_args()

    from tripwire.core import paths

    project_dir = args.project_dir.expanduser().resolve()
    plan_path = (
        project_dir
        / "instances"
        / "sessions"
        / args.session_id
        / "artifacts"
        / "plan.md"
    )
    if not plan_path.is_file():
        # v0.13.x put plan.md at instances/sessions/<sid>/plan.md (no artifacts/).
        # Try the legacy layout before giving up.
        legacy = project_dir / "instances" / "sessions" / args.session_id / "plan.md"
        if legacy.is_file():
            plan_path = legacy
        else:
            print(
                f"session {args.session_id}: plan.md not found at "
                f"{plan_path}; cannot append PM follow-up stub",
                file=sys.stderr,
            )
            return 1

    current = plan_path.read_text(encoding="utf-8")
    if _STUB_HEADING in current:
        print(
            f"  {plan_path}: PM follow-up section already present; no-op",
            file=sys.stderr,
        )
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    stub = _STUB_BODY_TEMPLATE.format(heading=_STUB_HEADING, timestamp=timestamp)

    # Append after a single trailing newline. Preserve any existing
    # trailing newline.
    if current and not current.endswith("\n"):
        current = current + "\n"
    plan_path.write_text(current + stub, encoding="utf-8")

    print(
        f"  appended PM follow-up stub to {plan_path}",
        file=sys.stderr,
    )

    # Silence unused-import warning while keeping `paths` available for
    # future expansion (e.g. resolving from a workflow-declared path).
    _ = paths

    return 0


if __name__ == "__main__":
    sys.exit(main())
