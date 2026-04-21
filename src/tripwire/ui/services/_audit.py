"""Shared audit-log helper for the mutation services.

Every write-path in ``tripwire.ui.services`` appends a single JSON-line
entry to ``~/.tripwire/logs/<project_id>.log`` so the UI can replay the
history of who did what to which project. The per-project log file is
opened lazily — no directory or file is created until the first mutation
lands.

``project_id`` is the same opaque 12-hex-char blake2s digest of the
absolute project path that :func:`tripwire.ui.services.project_service._project_id`
produces. We recompute it here rather than importing to avoid a cross-
service dependency on a module-private helper.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tripwire.ui.services._atomic_write import append_jsonl


def _project_id(project_dir: Path) -> str:
    """Return the 12-char hex digest the UI uses as a project identifier."""
    return hashlib.blake2s(
        str(project_dir.resolve()).encode(), digest_size=6
    ).hexdigest()


def audit_log_path(project_dir: Path) -> Path:
    """Return ``~/.tripwire/logs/<project_id>.log`` for *project_dir*.

    The ``TRIPWIRE_LOG_DIR`` env var overrides ``~/.tripwire/logs`` — this is
    the hook tests use to redirect audit writes into ``tmp_path`` without
    polluting the user's home directory.
    """
    override = os.environ.get("TRIPWIRE_LOG_DIR")
    root = Path(override) if override else Path.home() / ".tripwire" / "logs"
    return root / f"{_project_id(project_dir)}.log"


def write_audit_entry(
    project_dir: Path,
    action: str,
    *,
    result_summary: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    extras: dict[str, Any] | None = None,
) -> None:
    """Append one mutation record as a JSON line.

    The record shape matches the KUI-23 spec —
    ``{action, timestamp, before_state_snippet, after_state_snippet,
    result_summary}`` — plus an optional ``extras`` dict for service-
    specific context (e.g. the issue key, the session id).
    """
    record: dict[str, Any] = {
        "action": action,
        "timestamp": datetime.now(tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z"),
        "before_state_snippet": before or {},
        "after_state_snippet": after or {},
        "result_summary": result_summary,
    }
    if extras:
        record["extras"] = extras
    append_jsonl(audit_log_path(project_dir), record)


__all__ = ["audit_log_path", "write_audit_entry"]
