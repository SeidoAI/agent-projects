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

from pydantic import ValidationError

from tripwire.core import paths
from tripwire.core.event_emitter import EventEmitter, NullEmitter
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.models.session import AgentSession

logger = logging.getLogger(__name__)


class SessionLoadError(ValueError):
    """Raised when a session.yaml file fails to deserialise.

    Wraps pydantic's ``ValidationError`` so callers see a stable
    exception type and a single migration instruction. Name-blind:
    the offending key(s) are extracted from the pydantic error
    rather than checked by name, so the wrapper does not encode any
    knowledge of legacy session shapes.
    """


# Pre-v0.9.4 → canonical session status rewrites. Used to detect when
# a session file's ``status:`` field is a legacy alias so the loader
# can raise :class:`LegacySessionStatusError` and point the user at
# ``tripwire migrate status-values``.
_LEGACY_SESSION_STATUSES: frozenset[str] = frozenset(
    {
        "active",
        "waiting_for_ci",
        "waiting_for_review",
        "waiting_for_deploy",
        "re_engaged",
    }
)


class LegacySessionStatusError(ValueError):
    """Raised by :func:`load_session` when a legacy ``status:`` value is
    detected on disk.

    Wraps the originating :class:`pydantic.ValidationError` and points
    the user at ``tripwire migrate status-values``.
    """

    def __init__(self, path: Path, status: str) -> None:
        self.path = path
        self.status = status
        super().__init__(
            f"{path} carries a pre-v0.9.4 `status: {status}` value. "
            f"Run `tripwire migrate status-values` to rewrite legacy "
            f"issue and session statuses to the canonical taxonomy."
        )


def _legacy_session_status(exc: ValidationError, frontmatter: dict) -> str | None:
    """Return the legacy status string if *exc* is the enum-rejection
    for `status`, else None.
    """
    status = frontmatter.get("status")
    if not isinstance(status, str) or status not in _LEGACY_SESSION_STATUSES:
        return None
    for err in exc.errors():
        loc = err.get("loc") or ()
        if loc and loc[0] == "status":
            return status
    return None


def session_dir(project_dir: Path, session_id: str) -> Path:
    """Directory containing `session.yaml`, `plan.md`, `artifacts/`."""
    return paths.session_dir(project_dir, session_id)


def session_yaml_path(project_dir: Path, session_id: str) -> Path:
    """Path to the session YAML file inside its directory."""
    return paths.session_yaml_path(project_dir, session_id)


def load_session(project_dir: Path, session_id: str) -> AgentSession:
    """Load `sessions/<session_id>/session.yaml` into an AgentSession.

    Raises :class:`SessionLoadError` if pydantic's
    :class:`ValidationError` fires on the parsed frontmatter — most
    commonly when an old-shape session.yaml carries a key the current
    schema rejects. The wrapper extracts the offending key(s) from the
    pydantic error message and points at the regeneration path; it
    does not encode any knowledge of legacy field names.
    """
    path = session_yaml_path(project_dir, session_id)
    if not path.exists():
        raise FileNotFoundError(f"Session file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    try:
        return AgentSession.model_validate({**frontmatter, "body": body})
    except ValidationError as exc:
        legacy = _legacy_session_status(exc, frontmatter)
        if legacy is not None:
            raise LegacySessionStatusError(path, legacy) from exc
        offending = sorted(
            {".".join(str(part) for part in err["loc"]) for err in exc.errors()}
        )
        raise SessionLoadError(
            f"Could not load {path}: AgentSession schema rejected "
            f"{len(offending)} field(s): {offending}. The session.yaml "
            f"shape may be stale; re-spawn the session or rewrite by "
            f"hand to match `tripwire.models.session.AgentSession`."
        ) from exc


def save_session(
    project_dir: Path,
    session: AgentSession,
    *,
    emitter: EventEmitter | None = None,
    update_cache: bool = True,
) -> None:
    """Serialise an AgentSession to `sessions/<id>/session.yaml`.

    Creates the session directory if missing. Sets `updated_at` to now
    if it is unset. As of v0.9 (KUI-132 / A7), sessions are first-class
    nodes in the unified entity graph and emit `refs` edges to issues
    they touch — so the graph cache must be invalidated after a write,
    matching `save_issue`'s pattern. Batch writers that invalidate
    explicitly at the end of a transaction should pass
    `update_cache=False`.

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
    # KUI-126 / A1: omit default `version: 1`.
    if data.get("version") == 1:
        data.pop("version", None)
    text = serialize_frontmatter_body(data, session.body)
    path.write_text(text, encoding="utf-8")

    if update_cache:
        from tripwire.core.graph.cache import update_cache_for_file

        update_cache_for_file(project_dir, str(path.relative_to(project_dir)))

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

    Raises :class:`LegacySessionStatusError` if any session file holds a
    pre-v0.9.4 ``status:`` value, pointing the user at
    ``tripwire migrate status-values``.
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
        try:
            sessions.append(AgentSession.model_validate({**frontmatter, "body": body}))
        except ValidationError as exc:
            legacy = _legacy_session_status(exc, frontmatter)
            if legacy is not None:
                raise LegacySessionStatusError(yaml_path, legacy) from exc
            raise
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
