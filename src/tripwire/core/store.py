"""File-based CRUD for issues, project config, and comments.

This module is the only place that touches the filesystem for these entity
types. It uses the parser to split frontmatter from body and the model layer
to construct typed objects from the parsed dict.

Project config is read from `<project>/project.yaml` (no body, just YAML).
Issues live at `<project>/issues/<KEY>/issue.yaml` (directory layout; the
per-issue comments, developer notes, and verification artifacts live
alongside under `<project>/issues/<KEY>/`).
Comments live at `<project>/issues/<KEY>/comments/<sequence>-*.yaml`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from tripwire.core import paths
from tripwire.core.parser import (
    ParseError,
    parse_frontmatter_body,
    serialize_frontmatter_body,
)
from tripwire.models.comment import Comment
from tripwire.models.issue import Issue
from tripwire.models.project import ProjectConfig

# Backwards-compatible aliases — prefer importing from `tripwire.core.paths`.
ISSUES_DIRNAME = paths.ISSUES_DIR
PROJECT_CONFIG_FILENAME = paths.PROJECT_CONFIG
COMMENTS_DIRNAME = paths.COMMENTS_SUBDIR


# Pre-v0.9.4 → canonical issue status rewrites. Used here purely to
# decide whether a ValidationError on `status` was a legacy value (so
# the wrapper can point users at `migrate status-values`) and to
# document the mapping; the actual rewrite happens in the migrate
# command.
_LEGACY_ISSUE_STATUSES: frozenset[str] = frozenset(
    {"backlog", "todo", "in_progress", "done", "canceled"}
)


class LegacyIssueStatusError(ValueError):
    """Raised by :func:`load_issue` when a legacy ``status:`` value is
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


def _legacy_issue_status(exc: ValidationError, frontmatter: dict) -> str | None:
    """Return the legacy status string if *exc* is the enum-rejection
    for `status`, else None.
    """
    status = frontmatter.get("status")
    if not isinstance(status, str) or status not in _LEGACY_ISSUE_STATUSES:
        return None
    for err in exc.errors():
        loc = err.get("loc") or ()
        if loc and loc[0] == "status":
            return status
    return None


# ============================================================================
# Project config
# ============================================================================


class ProjectNotFoundError(FileNotFoundError):
    """Raised when `project.yaml` is missing from the expected location."""


def load_project(project_dir: Path) -> ProjectConfig:
    """Load `<project_dir>/project.yaml` into a ProjectConfig.

    Raises:
        ProjectNotFoundError: if project.yaml is missing.
        ValueError: if the file cannot be parsed.
    """
    path = paths.project_config_path(project_dir)
    if not path.exists():
        raise ProjectNotFoundError(
            f"project.yaml not found at {path}. Run `tripwire init` first."
        )
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"project.yaml must be a YAML mapping, got {type(raw).__name__}"
        )
    return ProjectConfig.model_validate(raw)


def save_project(project_dir: Path, config: ProjectConfig) -> None:
    """Write a ProjectConfig back to `<project_dir>/project.yaml`."""
    path = paths.project_config_path(project_dir)
    data = config.model_dump(mode="json", exclude_none=True)
    # KUI-126 / A1: omit default `version: 1` so existing files don't
    # sprout the field until a real contract bump.
    if data.get("version") == 1:
        data.pop("version", None)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


# ============================================================================
# Issues
# ============================================================================


def issue_path(project_dir: Path, key: str) -> Path:
    return paths.issue_path(project_dir, key)


def load_issue(project_dir: Path, key: str) -> Issue:
    """Load `<project_dir>/issues/<key>.yaml` into an Issue model.

    Raises :class:`LegacyIssueStatusError` (subclass of ``ValueError``)
    if the on-disk ``status:`` field is a pre-v0.9.4 legacy value
    (``backlog``/``todo``/``in_progress``/``done``/``canceled``).
    Generic :class:`pydantic.ValidationError` is left to propagate
    untouched for any other schema problem.
    """
    path = issue_path(project_dir, key)
    if not path.exists():
        raise FileNotFoundError(f"Issue file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    try:
        return Issue.model_validate({**frontmatter, "body": body})
    except ValidationError as exc:
        legacy = _legacy_issue_status(exc, frontmatter)
        if legacy is not None:
            raise LegacyIssueStatusError(path, legacy) from exc
        raise


def save_issue(project_dir: Path, issue: Issue, *, update_cache: bool = True) -> None:
    """Serialise an Issue to `<project_dir>/issues/<id>.yaml`.

    Sets `updated_at` to now if it is unset. If `update_cache` is True
    (the default), invalidates the graph cache for this file so the next
    read sees the new state. Batch writers that invalidate explicitly at
    the end of a transaction should pass `update_cache=False`.
    """
    if issue.updated_at is None:
        issue.updated_at = datetime.now()

    path = issue_path(project_dir, issue.id)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = issue.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    # KUI-126 / A1: omit default `version: 1`.
    if data.get("version") == 1:
        data.pop("version", None)
    text = serialize_frontmatter_body(data, issue.body)
    path.write_text(text, encoding="utf-8")

    if update_cache:
        from tripwire.core.graph.cache import update_cache_for_file

        update_cache_for_file(project_dir, str(path.relative_to(project_dir)))


def list_issues(project_dir: Path) -> list[Issue]:
    """Load every issue at `<project_dir>/issues/<KEY>/issue.yaml`.

    Files that fail to parse raise the parse error so callers can decide
    whether to skip them. The validator should be the gate that catches
    invalid files at scan time.

    Raises :class:`LegacyIssueStatusError` (subclass of ``ValueError``)
    if any issue file holds a pre-v0.9.4 ``status:`` value, pointing
    the user at ``tripwire migrate status-values``.
    """
    issues_dir = paths.issues_dir(project_dir)
    if not issues_dir.is_dir():
        return []
    issues: list[Issue] = []
    for idir in sorted(p for p in issues_dir.iterdir() if p.is_dir()):
        if idir.name.startswith("."):
            continue
        yaml_path = idir / paths.ISSUE_FILENAME
        if not yaml_path.is_file():
            continue
        text = yaml_path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter_body(text)
        try:
            issues.append(Issue.model_validate({**frontmatter, "body": body}))
        except ValidationError as exc:
            legacy = _legacy_issue_status(exc, frontmatter)
            if legacy is not None:
                raise LegacyIssueStatusError(yaml_path, legacy) from exc
            raise
    return issues


def issue_exists(project_dir: Path, key: str) -> bool:
    return issue_path(project_dir, key).exists()


# ============================================================================
# Comments
# ============================================================================


def comments_dir(project_dir: Path, issue_key: str) -> Path:
    return paths.comments_dir(project_dir, issue_key)


def load_comments(project_dir: Path, issue_key: str) -> list[Comment]:
    """Load every comment under `<project_dir>/issues/<key>/comments/`."""
    cdir = comments_dir(project_dir, issue_key)
    if not cdir.is_dir():
        return []
    comments: list[Comment] = []
    for path in sorted(cdir.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_frontmatter_body(text)
        comments.append(Comment.model_validate({**frontmatter, "body": body}))
    return comments


def save_comment(project_dir: Path, comment: Comment, filename: str) -> None:
    """Save one comment under `<project_dir>/issues/<key>/comments/<filename>`.

    The caller picks the filename (e.g. `001-start-2026-03-26.yaml`) so the
    sequence number convention is preserved.

    Comments don't contribute to the concept graph, so the graph cache is
    not invalidated here.
    """
    cdir = comments_dir(project_dir, comment.issue_key)
    cdir.mkdir(parents=True, exist_ok=True)
    path = cdir / filename
    data = comment.model_dump(mode="json", exclude={"body"}, exclude_none=True)
    # KUI-126 / A1: omit default `version: 1`.
    if data.get("version") == 1:
        data.pop("version", None)
    text = serialize_frontmatter_body(data, comment.body)
    path.write_text(text, encoding="utf-8")
