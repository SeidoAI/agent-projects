"""Enumerate JIT prompt fires for a session, with ack-marker join.

Reads ``.tripwire/events/jit_prompt_firings/<sid>/*.json`` (written by
``FileEmitter`` from the registry) and joins each entry against the
per-JIT-prompt ack marker at ``.tripwire/acks/<prompt_id>-<sid>.json``.

The CLI wrapper at ``cli/session.py:session_log_cmd`` calls
:func:`enumerate_fires` and renders each :class:`FireEntry` to stdout.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass
class FireEntry:
    """One JIT prompt fire for a session, with ack status joined.

    ``ack_status`` is one of ``"unacked"`` / ``"acked"`` /
    ``"acked (declared_no_findings)"`` / ``"acked (unreadable marker)"``.
    ``ack_detail`` is empty unless the ack carries fix-commit refs.
    """

    fired_at: str
    jit_prompt_id: str
    event: str
    escalated: bool
    ack_status: str
    ack_detail: str
    prompt_revealed: str | None
    unreadable: bool = False
    source_path: Path | None = None


def enumerate_fires(project_dir: Path, session_id: str) -> Iterator[FireEntry]:
    """Yield each fire for *session_id*, ack-status joined.

    Yields nothing if the firings directory is absent or empty. Each
    entry's ``unreadable=True`` flags a file that couldn't be parsed —
    the caller decides how to surface it.
    """
    fire_dir = project_dir / ".tripwire" / "events" / "jit_prompt_firings" / session_id
    if not fire_dir.is_dir():
        return

    for path in sorted(fire_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            yield FireEntry(
                fired_at="?",
                jit_prompt_id="?",
                event="?",
                escalated=False,
                ack_status="?",
                ack_detail="",
                prompt_revealed=None,
                unreadable=True,
                source_path=path,
            )
            continue

        prompt_id = payload.get("jit_prompt_id", "?")
        marker_path = (
            project_dir / ".tripwire" / "acks" / f"{prompt_id}-{session_id}.json"
        )
        ack_status = "unacked"
        ack_detail = ""
        if marker_path.is_file():
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                if marker.get("declared_no_findings"):
                    ack_status = "acked (declared_no_findings)"
                elif marker.get("fix_commits"):
                    fixes = marker["fix_commits"]
                    ack_status = "acked"
                    ack_detail = f"  fix_commits={','.join(fixes)}"
            except (OSError, json.JSONDecodeError):
                ack_status = "acked (unreadable marker)"

        yield FireEntry(
            fired_at=payload.get("fired_at", "?"),
            jit_prompt_id=prompt_id,
            event=payload.get("event", "?"),
            escalated=bool(payload.get("escalated", False)),
            ack_status=ack_status,
            ack_detail=ack_detail,
            prompt_revealed=payload.get("prompt_revealed"),
            source_path=path,
        )
