"""Single source of truth for project-state file paths.

Every entity directory and well-known file path used inside a keel-managed
project lives here. Other modules import from this module instead of
hardcoding strings, so that structural changes (renaming a directory,
moving artifacts) can be made in one place.

The `*_DIR` and `*_FILE` constants are relative paths (no leading slash).
The path-builder functions take the project root (`project_dir`) as their
first argument and return absolute `Path` objects.

Some constants here document layouts that are *transitional* — flagged
with comments so future migrations have a single place to update. See the
v0.5 architectural refactor plan for the migration sequence.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Top-level files
# ---------------------------------------------------------------------------

PROJECT_CONFIG = "project.yaml"
PROJECT_LOCK = ".keel.lock"
STANDARDS = "standards.md"
CLAUDE_MD = "CLAUDE.md"

# ---------------------------------------------------------------------------
# Entity directories (source of truth — written by agents)
# ---------------------------------------------------------------------------

ISSUES_DIR = "issues"

# Concept nodes are source entities — peers of issues and sessions.
# The derived graph cache lives separately at `graph/index.yaml`.
NODES_DIR = "nodes"

SESSIONS_DIR = "sessions"
AGENTS_DIR = "agents"
ENUMS_DIR = "enums"

# ---------------------------------------------------------------------------
# Plans (PM working directory)
# ---------------------------------------------------------------------------

PLANS_DIR = "plans"
PLANS_ARTIFACTS_DIR = "plans/artifacts"

# ---------------------------------------------------------------------------
# Documentation namespace
# ---------------------------------------------------------------------------

DOCS_DIR = "docs"

# Per-issue artifacts (comments, developer notes, verification) live
# alongside the issue YAML under `issues/<KEY>/`, matching the session
# pattern.

# ---------------------------------------------------------------------------
# Templates and orchestration
# ---------------------------------------------------------------------------

TEMPLATES_DIR = "templates"
TEMPLATES_ARTIFACTS_DIR = "templates/artifacts"
TEMPLATES_ARTIFACTS_MANIFEST = "templates/artifacts/manifest.yaml"
ISSUE_TEMPLATES_DIR = "issue_templates"
SESSION_TEMPLATES_DIR = "session_templates"
COMMENT_TEMPLATES_DIR = "comment_templates"
ORCHESTRATION_DIR = "orchestration"

# ---------------------------------------------------------------------------
# Derived graph cache (regenerable from source files)
# ---------------------------------------------------------------------------

GRAPH_CACHE = "graph/index.yaml"
GRAPH_LOCK = "graph/.index.lock"

# ---------------------------------------------------------------------------
# Per-entity sub-paths and filenames
# ---------------------------------------------------------------------------

COMMENTS_SUBDIR = "comments"
DEVELOPER_FILENAME = "developer.md"
VERIFIED_FILENAME = "verified.md"

# Sessions are directories: `sessions/<id>/session.yaml` plus `plan.md` and
# `artifacts/`. Enforced by `keel.core.session_store` since Phase 3.
SESSION_FILENAME = "session.yaml"
SESSION_PLAN = "plan.md"
SESSION_ARTIFACTS_SUBDIR = "artifacts"

# Issues are directories: `issues/<KEY>/issue.yaml` plus `comments/`,
# `developer.md`, `verified.md` alongside. Enforced by `keel.core.store`
# since Phase 4.
ISSUE_FILENAME = "issue.yaml"


# ---------------------------------------------------------------------------
# Path builders
# ---------------------------------------------------------------------------


def project_config_path(project_dir: Path) -> Path:
    return project_dir / PROJECT_CONFIG


def project_lock_path(project_dir: Path) -> Path:
    return project_dir / PROJECT_LOCK


def issues_dir(project_dir: Path) -> Path:
    return project_dir / ISSUES_DIR


def issue_dir(project_dir: Path, key: str) -> Path:
    """Per-issue directory: `issues/<key>/`. Contains `issue.yaml`,
    `comments/`, `developer.md`, `verified.md`."""
    return project_dir / ISSUES_DIR / key


def issue_path(project_dir: Path, key: str) -> Path:
    """Path to the issue YAML file at `issues/<key>/issue.yaml`."""
    return issue_dir(project_dir, key) / ISSUE_FILENAME


def comments_dir(project_dir: Path, key: str) -> Path:
    return issue_dir(project_dir, key) / COMMENTS_SUBDIR


def developer_md_path(project_dir: Path, key: str) -> Path:
    return issue_dir(project_dir, key) / DEVELOPER_FILENAME


def verified_md_path(project_dir: Path, key: str) -> Path:
    return issue_dir(project_dir, key) / VERIFIED_FILENAME


def nodes_dir(project_dir: Path) -> Path:
    return project_dir / NODES_DIR


def node_path(project_dir: Path, node_id: str) -> Path:
    return project_dir / NODES_DIR / f"{node_id}.yaml"


def sessions_dir(project_dir: Path) -> Path:
    return project_dir / SESSIONS_DIR


def session_dir(project_dir: Path, session_id: str) -> Path:
    return project_dir / SESSIONS_DIR / session_id


def session_yaml_path(project_dir: Path, session_id: str) -> Path:
    return session_dir(project_dir, session_id) / SESSION_FILENAME


def session_plan_path(project_dir: Path, session_id: str) -> Path:
    return session_dir(project_dir, session_id) / SESSION_PLAN


def session_artifacts_dir(project_dir: Path, session_id: str) -> Path:
    return session_dir(project_dir, session_id) / SESSION_ARTIFACTS_SUBDIR


def graph_cache_path(project_dir: Path) -> Path:
    return project_dir / GRAPH_CACHE


def graph_lock_path(project_dir: Path) -> Path:
    return project_dir / GRAPH_LOCK


def plans_artifacts_dir(project_dir: Path) -> Path:
    return project_dir / PLANS_ARTIFACTS_DIR


def templates_artifacts_manifest_path(project_dir: Path) -> Path:
    return project_dir / TEMPLATES_ARTIFACTS_MANIFEST
