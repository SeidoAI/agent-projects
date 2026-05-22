"""Post-write hook: append a JSON line to ``.tripwire/audit.jsonl``."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.workflow.schema import WorkflowRoute
from tripwire.models.session import AgentSession


def append_audit_record(
    project_dir: Path,
    *,
    session: AgentSession,
    route: WorkflowRoute,
    from_status: str,
    flags: dict,
    now: datetime | None = None,
) -> None:
    """Append a JSON line to ``.tripwire/audit.jsonl``.

    ``flags["action"]`` overrides the default ``transition`` action
    (e.g. ``session_reopen`` writes ``action: session_reopen``).

    Exceptions propagate. The executor wraps each post-write hook in a
    logged try/except — swallowing here too would silently hide bugs.
    """
    from tripwire.core.events.log import isoformat_z
    from tripwire.core.jsonl_log import append_jsonl
    from tripwire.core.session_reopen import _audit_path

    when = now or datetime.now(tz=timezone.utc)
    audit = _audit_path(project_dir)
    audit.parent.mkdir(parents=True, exist_ok=True)
    append_jsonl(
        audit,
        {
            "timestamp": isoformat_z(when),
            "action": flags.get("action", "transition"),
            "session_id": session.id,
            "route_id": route.id,
            "from_status": from_status,
            "to_status": route.to_ref,
            "reason": flags.get("reason"),
        },
        sort_keys=True,
        default=str,
    )
