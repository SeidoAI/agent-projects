"""File-based CRUD for agent sessions.

Sessions live at `<project>/sessions/<id>/session.yaml`. The session
directory contains:

- `session.yaml` — the session definition (frontmatter + optional body)
- `plan.md` — the implementation plan (required before phase `executing`)
- `artifacts/` — session artifacts produced during execution
- `comments/` — session-level messages

This module handles only the YAML file. Artifacts, plans, and comments
are accessed via their own path helpers in `tripwire.core.paths`.

The directory layout is enforced here: `list_sessions` only finds
sessions that have `session.yaml` in their directory. A flat
`sessions/<id>.yaml` is not recognised.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core import paths
from tripwire.core.event_emitter import EventEmitter, NullEmitter
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.models.session import AgentSession

logger = logging.getLogger(__name__)


def session_dir(project_dir: Path, session_id: str) -> Path:
    """Directory containing `session.yaml`, `plan.md`, `artifacts/`."""
    return paths.session_dir(project_dir, session_id)


def session_yaml_path(project_dir: Path, session_id: str) -> Path:
    """Path to the session YAML file inside its directory."""
    return paths.session_yaml_path(project_dir, session_id)


def load_session(project_dir: Path, session_id: str) -> AgentSession:
    """Load `sessions/<session_id>/session.yaml` into an AgentSession."""
    path = session_yaml_path(project_dir, session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return AgentSession.model_validate({**frontmatter, "body": body})


def save_session(
    project_dir: Path,
    session: AgentSession,
    *,
    emitter: EventEmitter | None = None,
) -> None:
    """Serialise an AgentSession to `sessions/<id>/session.yaml`.

    Creates the session directory if missing. Sets `updated_at` to now
    if it is unset. Does not invalidate the graph cache (sessions are
    not tracked in the concept graph).

    If *emitter* is supplied and the session's previously-persisted
    `status` differs from the new value, one ``status_transition`` event
    is emitted. The default `NullEmitter` keeps existing batch behaviour
    unchanged. See `docs/specs/2026-04-26-v08-handoff.md` §1.2.
    """
    prior_status = _read_persisted_status(project_dir, session.id)

    if session.updated_at is None:
        session.updated_at = datetime.now()

    path = session_yaml_path(project_dir, session.id)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = session.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    text = serialize_frontmatter_body(data, session.body)
    path.write_text(text, encoding="utf-8")

    if emitter is None:
        emitter = NullEmitter()
    if isinstance(emitter, NullEmitter):
        return
    if prior_status is None or prior_status == session.status:
        return
    _emit_status_transition(
        emitter,
        session_id=session.id,
        from_status=prior_status,
        to_status=session.status,
    )


def _read_persisted_status(project_dir: Path, session_id: str) -> str | None:
    """Return the status field of the on-disk session.yaml or None.

    Used to compute the `from_status` field in a `status_transition`
    event. The check is best-effort: a parse error or missing file
    means we have nothing to compare against, so no event fires.
    """
    path = session_yaml_path(project_dir, session_id)
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        frontmatter, _ = parse_frontmatter_body(text)
    except (OSError, ParseError):
        return None
    status = frontmatter.get("status")
    return status if isinstance(status, str) else None


def _emit_status_transition(
    emitter: EventEmitter,
    *,
    session_id: str,
    from_status: str,
    to_status: str,
) -> None:
    """Emit one `status_transition` event under `status_transitions/`."""
    fired_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "id": (f"evt-{fired_at}-status-{session_id}-{from_status}-to-{to_status}"),
        "kind": "status_transition",
        "fired_at": fired_at,
        "session_id": session_id,
        "from_status": from_status,
        "to_status": to_status,
    }
    try:
        emitter.emit("status_transitions", payload)
    except Exception:
        logger.exception("status_transition emission failed for %s", session_id)


def list_sessions(project_dir: Path) -> list[AgentSession]:
    """Load every session under `sessions/<id>/session.yaml`.

    Files that fail to parse raise the error; callers must decide whether
    to skip them. The validator loader swallows per-file errors and
    reports them as `session/parse_error` / `session/schema_invalid`.
    """
    sessions_root = paths.sessions_dir(project_dir)
    if not sessions_root.is_dir():
        return []
    sessions: list[AgentSession] = []
    for sdir in sorted(p for p in sessions_root.iterdir() if p.is_dir()):
        if sdir.name.startswith("."):
            continue
        yaml_path = sdir / paths.SESSION_FILENAME
        if not yaml_path.is_file():
            continue
        text = yaml_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter_body(text)
        sessions.append(AgentSession.model_validate({**frontmatter, "body": body}))
    return sessions


def session_exists(project_dir: Path, session_id: str) -> bool:
    return session_yaml_path(project_dir, session_id).is_file()


def delete_session(project_dir: Path, session_id: str) -> None:
    """Delete an entire session directory (yaml, plan, artifacts, comments).

    No-op if the directory does not exist.
    """
    sdir = session_dir(project_dir, session_id)
    if sdir.exists():
        shutil.rmtree(sdir)
