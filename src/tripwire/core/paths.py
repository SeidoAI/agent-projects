"""Single source of truth for project-state file paths.

Every entity directory and well-known file path used inside a tripwire-managed
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
PROJECT_LOCK = ".tripwire.lock"
STANDARDS = "standards.md"
CLAUDE_MD = "CLAUDE.md"

# ---------------------------------------------------------------------------
# Entity directories (source of truth — written by agents)
# ---------------------------------------------------------------------------

ISSUES_DIR = "issues"

# Concept nodes are source entities — peers of issues and sessions.
# The derived graph cache lives separately at `graph/index.yaml`.
NODES_DIR = "nodes"

INBOX_DIR = "inbox"
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
# `artifacts/`. Enforced by `tripwire.core.session_store` since Phase 3.
SESSION_FILENAME = "session.yaml"
SESSION_PLAN = "plan.md"
SESSION_ARTIFACTS_SUBDIR = "artifacts"

# Handoff record written at session launch (v0.6a): sessions/<id>/handoff.yaml.
HANDOFF_FILENAME = "handoff.yaml"

# Workspace-level constants (v0.6b).
# A workspace is a separate git repo containing canonical shared nodes
# for N member projects. See
# docs/specs/2026-04-15-keel-workspace.md.
WORKSPACE_YAML = "workspace.yaml"
WORKSPACE_NODES_DIR = "nodes"  # same name as in-project nodes/, at workspace root
MERGE_BRIEFS_DIR = ".tripwire/merge-briefs"

# Issues are directories: `issues/<KEY>/issue.yaml` plus `comments/`,
# `developer.md`, `verified.md` alongside. Enforced by `tripwire.core.store`
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
    """Resolve the plan.md path for a session.

    Always ``sessions/<sid>/artifacts/plan.md`` per the manifest's
    subdir-aware artifact contract. The pre-v0.8 flat-layout fallback
    was removed in KUI-158 once every session was migrated.
    """
    return (
        session_dir(project_dir, session_id) / SESSION_ARTIFACTS_SUBDIR / SESSION_PLAN
    )


def session_artifacts_dir(project_dir: Path, session_id: str) -> Path:
    return session_dir(project_dir, session_id) / SESSION_ARTIFACTS_SUBDIR


def handoff_path(project_dir: Path, session_id: str) -> Path:
    """Path to sessions/<session_id>/handoff.yaml (v0.6a)."""
    return session_dir(project_dir, session_id) / HANDOFF_FILENAME


def inbox_dir(project_dir: Path) -> Path:
    return project_dir / INBOX_DIR


def inbox_entry_path(project_dir: Path, entry_id: str) -> Path:
    return project_dir / INBOX_DIR / f"{entry_id}.md"


def graph_cache_path(project_dir: Path) -> Path:
    return project_dir / GRAPH_CACHE


def graph_lock_path(project_dir: Path) -> Path:
    return project_dir / GRAPH_LOCK


def plans_artifacts_dir(project_dir: Path) -> Path:
    return project_dir / PLANS_ARTIFACTS_DIR


def templates_artifacts_manifest_path(project_dir: Path) -> Path:
    return project_dir / TEMPLATES_ARTIFACTS_MANIFEST


# ---------------------------------------------------------------------------
# Workspace path builders (v0.6b)
# ---------------------------------------------------------------------------


def workspace_yaml_path(workspace_dir: Path) -> Path:
    """Path to workspace.yaml at the workspace root."""
    return workspace_dir / WORKSPACE_YAML


def workspace_nodes_dir(workspace_dir: Path) -> Path:
    """Path to the workspace's shared nodes/ directory."""
    return workspace_dir / WORKSPACE_NODES_DIR


def workspace_node_path(workspace_dir: Path, node_id: str) -> Path:
    """Path to a specific workspace node YAML file."""
    return workspace_nodes_dir(workspace_dir) / f"{node_id}.yaml"


def workspace_lock_path(workspace_dir: Path) -> Path:
    """Path to the workspace-level lock file.

    Reuses ``PROJECT_LOCK`` filename — the lock helper works on any
    directory, and workspaces follow the same locking convention.
    """
    return workspace_dir / PROJECT_LOCK


def merge_briefs_dir(project_dir: Path) -> Path:
    """Path to a project's merge-briefs directory.

    Briefs live in .tripwire/merge-briefs/ (hidden) so they don't clutter
    the project tree. ``tripwire workspace pull`` writes briefs here when
    a 3-way merge produces conflicts; ``merge-resolve`` removes them.
    """
    return project_dir / MERGE_BRIEFS_DIR


def merge_brief_path(project_dir: Path, node_id: str) -> Path:
    """Path to a specific merge brief file for a node."""
    return merge_briefs_dir(project_dir) / f"{node_id}.yaml"


# ---------------------------------------------------------------------------
# Project override locations (v0.7b)
# ---------------------------------------------------------------------------
#
# A project can customise slash commands and spawn config by dropping files
# into its `.tripwire/` directory. Override > packaged default.

TRIPWIRE_DIR = ".tripwire"
TRIPWIRE_COMMANDS_SUBDIR = ".tripwire/commands"
TRIPWIRE_SPAWN_SUBDIR = ".tripwire/spawn"


def tripwire_dir(project_dir: Path) -> Path:
    """Per-project override root: `<project>/.tripwire/`."""
    return project_dir / TRIPWIRE_DIR


def project_commands_dir(project_dir: Path) -> Path:
    return project_dir / TRIPWIRE_COMMANDS_SUBDIR


def project_spawn_dir(project_dir: Path) -> Path:
    return project_dir / TRIPWIRE_SPAWN_SUBDIR


def resolve_command_path(project_dir: Path, command_name: str) -> Path:
    """Resolve a slash command file, preferring project override.

    Lookup order:
      1. `<project>/.tripwire/commands/<command>.md`
      2. `src/tripwire/templates/commands/<command>.md` (packaged default)
    """
    override = project_commands_dir(project_dir) / f"{command_name}.md"
    if override.is_file():
        return override
    import tripwire

    return (
        Path(tripwire.__file__).parent / "templates" / "commands" / f"{command_name}.md"
    )
