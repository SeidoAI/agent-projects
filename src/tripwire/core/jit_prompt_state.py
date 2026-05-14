"""Write JIT prompt ack/bypass markers for the runtime registry."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core import paths


def write_jit_prompt_ack_marker(
    *,
    project_dir: Path,
    session_id: str,
    jit_prompt_id: str,
    fix_commits: list[str],
    declared_no_findings: bool,
    workflow_id: str = "coding-session",
) -> Path:
    """Write the JIT prompt ack marker, validating substantiveness.

    ``workflow_id`` defaults to ``coding-session`` because that is the
    only workflow that produces JIT prompt fires today; future
    workflows pass their id explicitly when they begin firing prompts.
    """
    if not fix_commits and not declared_no_findings:
        raise ValueError(
            "JIT prompt ack requires substance: pass at least one "
            "`--fix-commit <sha>` OR `--declared-no-findings`. The "
            "marker substantiveness check would reject an empty ack."
        )

    marker = paths.ack_marker_path(
        project_dir, workflow_id, session_id, jit_prompt_id
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "jit_prompt_id": jit_prompt_id,
        "session_id": session_id,
        "acked_at": datetime.now(tz=timezone.utc).isoformat(),
        "fix_commits": list(fix_commits),
        "declared_no_findings": bool(declared_no_findings),
    }
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return marker


def record_bypass(*, project_dir: Path, session_id: str, event: str) -> None:
    """Append a one-line audit entry when ``--no-jit-prompts`` is used."""
    audit_dir = project_dir / ".tripwire" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "jit_prompt_bypass.log"
    stamp = datetime.now(tz=timezone.utc).isoformat()
    line = f"{stamp}\t{event}\t{session_id}\t--no-jit-prompts\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
