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
    """Load `<project_dir>/issues/<key>.yaml` into an Issue model."""
    path = issue_path(project_dir, key)
    if not path.exists():
        raise FileNotFoundError(f"Issue file not found: {path}")
    text = path.read_text(encoding="utf-8")
    try:
        frontmatter, body = parse_frontmatter_body(text)
    except ParseError as exc:
        raise ValueError(f"Could not parse {path}: {exc}") from exc
    return Issue.model_validate({**frontmatter, "body": body})


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
    text = serialize_frontmatter_body(data, issue.body)
    path.write_text(text, encoding="utf-8")

    if update_cache:
        from tripwire.core.graph_cache import update_cache_for_file

        update_cache_for_file(project_dir, str(path.relative_to(project_dir)))


def list_issues(project_dir: Path) -> list[Issue]:
    """Load every issue at `<project_dir>/issues/<KEY>/issue.yaml`.

    Files that fail to parse raise the parse error so callers can decide
    whether to skip them. The validator should be the gate that catches
    invalid files at scan time.
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
        issues.append(Issue.model_validate({**frontmatter, "body": body}))
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
    text = serialize_frontmatter_body(data, comment.body)
    path.write_text(text, encoding="utf-8")
