"""Write JIT prompt ack/bypass markers for the runtime registry.

The JIT prompt enforcement loop checks for an ack marker at
``.tripwire/acks/<jit_prompt_id>-<session_id>.json`` to decide whether
a fired JIT prompt has been responded to. Bypasses (``--no-jit-prompts``)
get a separate audit-log entry under ``.tripwire/audit/``.

The CLI wrappers in ``cli/session.py`` (``session complete``) call
:func:`write_jit_prompt_ack_marker` / :func:`record_bypass`; raised
``ValueError`` is caught + re-raised as ``click.ClickException``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def write_jit_prompt_ack_marker(
    *,
    project_dir: Path,
    session_id: str,
    jit_prompt_id: str,
    fix_commits: list[str],
    declared_no_findings: bool,
) -> Path:
    """Write the JIT prompt ack marker, validating substantiveness.

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
            "JIT prompt ack requires substance: pass at least one "
            "`--fix-commit <sha>` OR `--declared-no-findings`. The "
            "marker substantiveness check would reject an empty ack."
        )

    marker = (
        project_dir / ".tripwire" / "acks" / f"{jit_prompt_id}-{session_id}.json"
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
    """Append a one-line audit entry when ``--no-jit-prompts`` is used.

    The audit log is the only durable record of the bypass — without it,
    an agent could opt out of the JIT prompt silently and the PM review
    would never know.
    """
    audit_dir = project_dir / ".tripwire" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    log_path = audit_dir / "jit_prompt_bypass.log"
    stamp = datetime.now(tz=timezone.utc).isoformat()
    line = f"{stamp}\t{event}\t{session_id}\t--no-jit-prompts\n"
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(line)
