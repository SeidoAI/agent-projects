"""Write tripwire ack/bypass markers for the runtime registry.

The tripwire framework's enforcement loop checks for an ack marker at
``.tripwire/acks/<tripwire_id>-<session_id>.json`` to decide whether
a fired tripwire has been responded to. Bypasses (``--no-tripwires``)
get a separate audit-log entry under ``.tripwire/audit/``.

The CLI wrappers in ``cli/session.py`` (``session complete``) call
:func:`write_ack_marker` / :func:`record_bypass`; raised
``ValueError`` is caught + re-raised as ``click.ClickException``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_ack_marker(
    *,
    project_dir: Path,
    session_id: str,
    tripwire_id: str,
    fix_commits: list[str],
    declared_no_findings: bool,
) -> Path:
    """Write the tripwire ack marker, validating substantiveness.

    Raises:
        ValueError: caller didn't supply at least one ``fix_commit`` OR
            ``declared_no_findings=True``. The marker substantiveness
            check would reject the same case at the next fire, so this
            surfaces immediately rather than letting the agent "ack"
            something that won't unblock.

    Returns the on-disk path of the written marker.
    """
    if not fix_commits and not declared_no_findings:
        raise ValueError(
            "Tripwire ack requires substance: pass at least one "
            "`--fix-commit <sha>` OR `--declared-no-findings`. The "
            "marker substantiveness check would reject an empty ack."
        )

    marker = project_dir / ".tripwire" / "acks" / f"{tripwire_id}-{session_id}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tripwire_id": tripwire_id,
        "session_id": session_id,
        "acked_at": datetime.now(tz=timezone.utc).isoformat(),
        "fix_commits": list(fix_commits),
        "declared_no_findings": bool(declared_no_findings),
    }
    marker.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return marker


def record_bypass(*, project_dir: Path, session_id: str, event: str) -> None:
    """Append a one-line audit entry when ``--no-tripwires`` is used.

    The audit log is the only durable record of the bypass — without it,
    an agent could opt out of the tripwire silently and the PM review
    would never know.
    """
    audit_dir = project_dir / ".tripwire" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "tripwire_bypass.log"
    stamp = datetime.now(tz=timezone.utc).isoformat()
    line = f"{stamp}\t{event}\t{session_id}\t--no-tripwires\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
