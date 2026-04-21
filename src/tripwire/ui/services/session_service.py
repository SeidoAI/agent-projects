"""Session read service — list + detail.

Walks ``<project>/sessions/<id>/`` directories and surfaces summaries +
details including ``plan.md`` contents, task-checklist progress, and
artifact presence per the project's ``templates/artifacts/manifest.yaml``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field

from tripwire.core import paths
from tripwire.core.parser import ParseError, parse_frontmatter_body
from tripwire.models.manifest import ArtifactManifest
from tripwire.models.session import AgentSession
from tripwire.models.session import RepoBinding as CoreRepoBinding

logger = logging.getLogger("tripwire.ui.services.session_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TaskProgress(BaseModel):
    """Completed vs total rows parsed from ``task-checklist.md``."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    done: int = 0
    total: int = 0


class RepoBinding(BaseModel):
    """Flattened session repo binding."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    repo: str
    base_branch: str
    branch: str | None = None
    pr_number: int | None = None


class SessionSummary(BaseModel):
    """Lightweight session descriptor for list views."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    name: str
    agent: str
    status: str
    issues: list[str] = Field(default_factory=list)
    estimated_size: str | None = None
    blocked_by_sessions: list[str] = Field(default_factory=list)
    repos: list[RepoBinding] = Field(default_factory=list)
    current_state: str | None = None
    re_engagement_count: int = 0
    task_progress: TaskProgress = Field(default_factory=TaskProgress)


class SessionDetail(SessionSummary):
    """Full session detail."""

    plan_md: str = ""
    key_files: list[str] = Field(default_factory=list)
    docs: list[str] = Field(default_factory=list)
    grouping_rationale: str | None = None
    engagements: list[dict[str, Any]] = Field(default_factory=list)
    artifact_status: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_TASK_CHECKLIST_FILENAME = "task-checklist.md"

# Match a Markdown table row with a status cell.
# Example: `| #1 | Do thing | done |` → status = "done"
# Also accepts checkbox-style bullets: `- [x] done thing`.
_TABLE_ROW_RE = re.compile(
    r"^\s*\|\s*(?P<cols>.*?)\s*\|?\s*$"
)
_BULLET_ROW_RE = re.compile(r"^\s*[-*]\s*\[(?P<mark>[ xX])\]\s+")


def _parse_task_checklist(text: str) -> TaskProgress:
    """Parse a ``task-checklist.md`` body into completed + total row counts.

    Accepts two formats:

    **Table** — one row per task, with a final ``status`` cell containing
    values like ``todo`` / ``in_progress`` / ``done``. The status enum
    is project-specific; we count ``done`` (case-insensitive) as complete.
    The header + separator lines are skipped.

    **Checkbox list** — markdown bullets like ``- [x] finished`` and
    ``- [ ] pending``. Counts the checked ones as complete.

    Returns ``TaskProgress(done=0, total=0)`` when the file has no
    recognisable rows.
    """
    done = 0
    total = 0

    # Table detection: scan lines that look like table rows.
    table_rows: list[list[str]] = []
    for line in text.splitlines():
        m = _TABLE_ROW_RE.match(line)
        if m is None:
            continue
        cols = [c.strip() for c in m.group("cols").split("|")]
        # Separator rows like `|---|---|---|` have empty cells or dashes.
        if all(not c or set(c) <= {"-", ":"} for c in cols):
            continue
        table_rows.append(cols)

    # Strip the header if the second row is all dashes in the original.
    # Simpler heuristic: treat first row as header if the rest share an
    # "in_progress" / "done" / "todo" token in the last column.
    parsed_any = False
    if len(table_rows) >= 2:
        header = [c.lower() for c in table_rows[0]]
        data_rows = table_rows[1:]
        # Look for a status-shaped column name.
        status_idx: int | None = None
        for i, h in enumerate(header):
            if h in {"status", "state"}:
                status_idx = i
                break
        if status_idx is None:
            status_idx = len(header) - 1

        for row in data_rows:
            if status_idx >= len(row):
                continue
            cell = row[status_idx].strip().lower()
            if not cell:
                continue
            total += 1
            if cell == "done":
                done += 1
            parsed_any = True

    if parsed_any:
        return TaskProgress(done=done, total=total)

    # Fallback: checkbox bullets.
    for line in text.splitlines():
        m = _BULLET_ROW_RE.match(line)
        if m is None:
            continue
        total += 1
        if m.group("mark").lower() == "x":
            done += 1

    return TaskProgress(done=done, total=total)


def _load_manifest(project_dir: Path) -> ArtifactManifest | None:
    """Return the parsed manifest, or ``None`` if missing / invalid."""
    path = paths.templates_artifacts_manifest_path(project_dir)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        logger.warning("manifest yaml error at %s: %s", path, exc)
        return None
    try:
        return ArtifactManifest.model_validate(raw)
    except ValueError as exc:
        logger.warning("manifest schema error at %s: %s", path, exc)
        return None


def _read_plan(project_dir: Path, session_id: str) -> str:
    plan_path = paths.session_plan_path(project_dir, session_id)
    if not plan_path.is_file():
        return ""
    return plan_path.read_text(encoding="utf-8")


def _read_task_progress(project_dir: Path, session_id: str) -> TaskProgress:
    artifacts_dir = paths.session_artifacts_dir(project_dir, session_id)
    # task-checklist.md can live either inside artifacts/ or at the session
    # root — accept both to match existing session layouts.
    for candidate in (
        artifacts_dir / _TASK_CHECKLIST_FILENAME,
        paths.session_dir(project_dir, session_id) / _TASK_CHECKLIST_FILENAME,
    ):
        if candidate.is_file():
            return _parse_task_checklist(candidate.read_text(encoding="utf-8"))
    return TaskProgress()


def _artifact_status(
    project_dir: Path,
    session_id: str,
    manifest: ArtifactManifest | None,
) -> dict[str, str]:
    if manifest is None:
        return {}
    sdir = paths.session_dir(project_dir, session_id)
    artifacts_dir = paths.session_artifacts_dir(project_dir, session_id)
    out: dict[str, str] = {}
    for entry in manifest.artifacts:
        present = (artifacts_dir / entry.file).is_file() or (
            sdir / entry.file
        ).is_file()
        out[entry.name] = "present" if present else "missing"
    return out


def _flatten_repo(repo: CoreRepoBinding) -> RepoBinding:
    return RepoBinding(
        repo=repo.repo,
        base_branch=repo.base_branch,
        branch=repo.branch,
        pr_number=repo.pr_number,
    )


def _build_summary(
    project_dir: Path,
    session: AgentSession,
) -> SessionSummary:
    return SessionSummary(
        id=session.id,
        name=session.name,
        agent=session.agent,
        status=session.status,
        issues=list(session.issues),
        estimated_size=session.estimated_size,
        blocked_by_sessions=list(session.blocked_by_sessions),
        repos=[_flatten_repo(r) for r in session.repos],
        current_state=session.current_state,
        re_engagement_count=max(len(session.engagements) - 1, 0),
        task_progress=_read_task_progress(project_dir, session.id),
    )


def _iter_session_dirs(project_dir: Path) -> list[Path]:
    """Return session directories, skipping hidden ones."""
    sessions_root = paths.sessions_dir(project_dir)
    if not sessions_root.is_dir():
        return []
    return sorted(
        p
        for p in sessions_root.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def _try_load(session_yaml: Path) -> AgentSession | None:
    """Parse a session.yaml, logging + skipping on any failure."""
    try:
        text = session_yaml.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s: %s", session_yaml, exc)
        return None
    try:
        fm, body = parse_frontmatter_body(text)
    except ParseError as exc:
        logger.warning("Parse error in %s: %s", session_yaml, exc)
        return None
    try:
        return AgentSession.model_validate({**fm, "body": body})
    except ValueError as exc:
        logger.warning("Schema error in %s: %s", session_yaml, exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_sessions(
    project_dir: Path,
    *,
    status: str | None = None,
) -> list[SessionSummary]:
    """Return every session under ``sessions/*/session.yaml`` as a summary.

    Broken files (IO / parse / schema errors) are skipped with a warning
    log rather than raising — a corrupt session.yaml should not take
    down the whole list.
    """
    summaries: list[SessionSummary] = []
    for sdir in _iter_session_dirs(project_dir):
        session_yaml = sdir / paths.SESSION_FILENAME
        if not session_yaml.is_file():
            continue
        session = _try_load(session_yaml)
        if session is None:
            continue
        if status is not None and session.status != status:
            continue
        summaries.append(_build_summary(project_dir, session))
    return summaries


def get_session(project_dir: Path, session_id: str) -> SessionDetail:
    """Return :class:`SessionDetail` for *session_id*.

    Raises :class:`FileNotFoundError` if the session directory or
    ``session.yaml`` is missing. Parse/schema errors propagate as
    :class:`ValueError` — the route translates those to 500.
    """
    session_yaml = paths.session_yaml_path(project_dir, session_id)
    if not session_yaml.is_file():
        raise FileNotFoundError(f"Session not found: {session_yaml}")

    text = session_yaml.read_text(encoding="utf-8")
    try:
        fm, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {session_yaml}: {exc}") from exc
    session = AgentSession.model_validate({**fm, "body": body})

    summary = _build_summary(project_dir, session)
    manifest = _load_manifest(project_dir)

    # TODO-v2: the engagements list is a v2-container-runtime placeholder.
    # Per KUI-18 execution constraint: "v1 it's always empty. Do not guess
    # at its shape — leave it as [] with a clear TODO-v2 comment." The
    # `re_engagement_count` scalar is still derived from whatever the
    # session.yaml has on disk (that's just a count).
    return SessionDetail(
        **summary.model_dump(),
        plan_md=_read_plan(project_dir, session_id),
        key_files=list(session.key_files),
        docs=list(session.docs or []),
        grouping_rationale=session.grouping_rationale,
        engagements=[],
        artifact_status=_artifact_status(project_dir, session_id, manifest),
    )


__all__ = [
    "RepoBinding",
    "SessionDetail",
    "SessionSummary",
    "TaskProgress",
    "get_session",
    "list_sessions",
]
