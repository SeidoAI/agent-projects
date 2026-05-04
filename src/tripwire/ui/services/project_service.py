"""Project auto-discovery service.

Scans the filesystem for ``project.yaml`` files and returns lightweight
summaries. Results are cached for 60 seconds; call ``reload_project_index()``
to force a rescan.

Also exposes :func:`list_projects` / :func:`get_project` — the higher-level
read APIs used by :mod:`tripwire.ui.routes.projects` for the
``/api/projects`` endpoints.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from tripwire.ui.config import UserConfig, load_user_config

logger = logging.getLogger("tripwire.ui.services.project_service")

_CACHE_TTL_SECONDS = 60

# Directories to never descend into during the walk.
_PRUNE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        ".claude",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)

# Common locations to scan when config has no project_roots.
_FALLBACK_ROOTS: tuple[str, ...] = ("Code", "code", "dev", "projects")


class ProjectSummary(BaseModel):
    """Lightweight project descriptor returned by discovery."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    name: str
    key_prefix: str
    dir: str
    phase: str
    issue_count: int
    node_count: int
    session_count: int


class ProjectDetail(ProjectSummary):
    """Full project descriptor returned by :func:`get_project`.

    Extends :class:`ProjectSummary` with every field a route may surface
    from ``project.yaml``. New :class:`ProjectConfig` fields flow through
    automatically via :meth:`pydantic.BaseModel.model_dump`.
    """

    description: str | None = None
    base_branch: str
    environments: list[str]
    repos: dict[str, dict]
    statuses: list[str]
    status_transitions: dict[str, list[str]]
    label_categories: dict[str, list[str]]
    graph: dict
    orchestration: dict
    next_issue_number: int
    next_session_number: int


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_discovery_cache: tuple[float, list[ProjectSummary]] | None = None
_project_index: dict[str, Path] = {}
# True when the server was started with explicit `--project-dir` paths.
# In that mode discovery is *pinned* — wider scans (CWD, project_roots,
# fallback paths) are bypassed so the user only sees the project(s) they
# asked for.
_pinned: bool = False


def _project_id(abs_dir: Path) -> str:
    return hashlib.blake2s(str(abs_dir).encode(), digest_size=6).hexdigest()


def _count_issues(project_dir: Path) -> int:
    issues = project_dir / "issues"
    if not issues.is_dir():
        return 0
    return sum(
        1 for p in issues.iterdir() if p.is_dir() and (p / "issue.yaml").is_file()
    )


def _count_nodes(project_dir: Path) -> int:
    nodes = project_dir / "nodes"
    if not nodes.is_dir():
        return 0
    return sum(1 for p in nodes.glob("*.yaml"))


def _count_sessions(project_dir: Path) -> int:
    sessions = project_dir / "sessions"
    if not sessions.is_dir():
        return 0
    return sum(1 for p in sessions.iterdir() if p.is_dir())


def _try_load_summary(abs_dir: Path) -> ProjectSummary | None:
    """Attempt to load a project summary from *abs_dir*.

    Returns ``None`` and logs a warning on any failure.
    """
    from tripwire.core.store import load_project

    try:
        config = load_project(abs_dir)
    except Exception as exc:
        logger.warning("Skipping %s: %s", abs_dir, exc)
        return None

    return ProjectSummary(
        id=_project_id(abs_dir),
        name=config.name,
        key_prefix=config.key_prefix,
        dir=str(abs_dir),
        phase=config.phase.value,
        issue_count=_count_issues(abs_dir),
        node_count=_count_nodes(abs_dir),
        session_count=_count_sessions(abs_dir),
    )


def _is_worktree_copy(project_dir: Path) -> bool:
    """Return True for common Tripwire/Git worktree project copies."""
    name = project_dir.name
    return name.startswith("worktree-") or "-wt-" in name


def _prefer_project_summary(
    existing: ProjectSummary, candidate: ProjectSummary
) -> ProjectSummary:
    """Pick the canonical summary when two paths share one project identity."""
    existing_path = Path(existing.dir)
    candidate_path = Path(candidate.dir)
    existing_is_worktree = _is_worktree_copy(existing_path)
    candidate_is_worktree = _is_worktree_copy(candidate_path)

    if existing_is_worktree != candidate_is_worktree:
        return candidate if not candidate_is_worktree else existing

    return candidate if str(candidate_path) < str(existing_path) else existing


def _deduplicate_summaries_by_identity(
    summaries: list[ProjectSummary],
) -> list[ProjectSummary]:
    """Collapse path-level duplicates for the same logical Tripwire project."""
    by_identity: dict[tuple[str, str], ProjectSummary] = {}

    for summary in summaries:
        key = (summary.name, summary.key_prefix)
        existing = by_identity.get(key)
        if existing is None:
            by_identity[key] = summary
            continue

        preferred = _prefer_project_summary(existing, summary)
        if preferred is not existing:
            by_identity[key] = preferred
        logger.info(
            "Collapsed duplicate project identity %s/%s: kept %s, skipped %s",
            summary.name,
            summary.key_prefix,
            preferred.dir,
            summary.dir if preferred is existing else existing.dir,
        )

    return list(by_identity.values())


def _should_prune(dirname: str) -> bool:
    return dirname in _PRUNE_DIRS or dirname.startswith(".")


def _find_projects_in_root(root: Path, max_depth: int) -> list[Path]:
    """Walk *root* up to *max_depth* levels looking for ``project.yaml``."""
    found: list[Path] = []
    if not root.is_dir():
        return found

    if (root / "project.yaml").is_file():
        found.append(root)

    if max_depth < 2:
        return found

    try:
        children = sorted(root.iterdir())
    except PermissionError:
        return found

    for child in children:
        if not child.is_dir() or _should_prune(child.name):
            continue
        if (child / "project.yaml").is_file():
            found.append(child)
    return found


def discover_projects(config: UserConfig) -> list[ProjectSummary]:
    """Discover tripwire projects and return their summaries.

    Results are cached for 60 seconds. The search order is:

    1. Current working directory (depth 1).
    2. Each ``config.project_roots`` entry (depth 2).
    3. If ``project_roots`` is empty, common fallback locations (depth 2).
    """
    global _discovery_cache, _project_index

    now = time.monotonic()
    if _discovery_cache is not None:
        cached_at, cached_results = _discovery_cache
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached_results

    if _pinned:
        # Started with --project-dir; surface only the seeded paths.
        summaries: list[ProjectSummary] = []
        for d in _project_index.values():
            summary = _try_load_summary(d)
            if summary is not None:
                summaries.append(summary)
        summaries = _deduplicate_summaries_by_identity(summaries)
        _discovery_cache = (now, summaries)
        return summaries

    seen: set[Path] = set()
    candidates: list[Path] = []

    def _add(dirs: list[Path]) -> None:
        for d in dirs:
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(resolved)

    # 1. CWD — depth 1 only
    _add(_find_projects_in_root(Path.cwd(), max_depth=1))

    # 2. Configured project roots — depth 2
    for root in config.project_roots:
        _add(_find_projects_in_root(root, max_depth=2))

    # 3. Fallback roots if no explicit roots configured
    if not config.project_roots:
        home = Path.home()
        for name in _FALLBACK_ROOTS:
            _add(_find_projects_in_root(home / name, max_depth=2))

    # Build summaries (the variable is also used in the pinned
    # branch above; mypy reads both branches, hence the bare
    # assignment here to avoid a `[no-redef]` collision).
    summaries = []
    for project_dir in candidates:
        summary = _try_load_summary(project_dir)
        if summary is not None:
            summaries.append(summary)

    summaries = _deduplicate_summaries_by_identity(summaries)
    index = {summary.id: Path(summary.dir) for summary in summaries}

    _discovery_cache = (now, summaries)
    _project_index = index
    return summaries


def get_project_dir(project_id: str) -> Path | None:
    """Return the directory for *project_id*, or ``None`` if unknown."""
    return _project_index.get(project_id)


def seed_project_index(project_dirs: list[Path]) -> None:
    """Populate the project index from an explicit list of directories.

    Used by ``start_server`` when the CLI's ``--project-dir`` flag bypasses
    ``discover_projects()``. When called with a non-empty list this also
    *pins* discovery to those paths — subsequent ``discover_projects``
    calls return only the seeded set instead of widening to CWD,
    ``config.project_roots`` and the fallback locations.
    """
    global _project_index, _pinned, _discovery_cache
    for d in project_dirs:
        resolved = d.resolve()
        _project_index[_project_id(resolved)] = resolved
    if project_dirs:
        _pinned = True
        # Drop any stale wider cache so the next read reflects the pin.
        _discovery_cache = None


def reload_project_index() -> None:
    """Clear the discovery cache and unpin so the next call rescans."""
    global _discovery_cache, _project_index, _pinned
    _discovery_cache = None
    _project_index = {}
    _pinned = False


# ---------------------------------------------------------------------------
# High-level read API used by /api/projects routes
# ---------------------------------------------------------------------------


def find_project_by_identity(name: str, key_prefix: str) -> ProjectSummary:
    """Return the first project whose name and key_prefix match.

    Tries the cached discovery first; if nothing matches, forces a rescan.
    Raises ``KeyError`` when no match is found after rescanning.
    """
    for summary in list_projects():
        if summary.name == name and summary.key_prefix == key_prefix:
            return summary
    if not _pinned:
        # Don't unpin a server that was scoped via --project-dir.
        reload_project_index()
        for summary in list_projects():
            if summary.name == name and summary.key_prefix == key_prefix:
                return summary
    raise KeyError(f"name={name!r} key_prefix={key_prefix!r}")


def list_projects() -> list[ProjectSummary]:
    """Return every discovered project as a :class:`ProjectSummary`.

    Loads the user config lazily on each call — cheap, and the in-memory
    discovery cache (60s TTL) absorbs repeated route hits.
    """
    return discover_projects(load_user_config())


def get_project(project_id: str) -> ProjectDetail:
    """Return full detail for *project_id*.

    The project index is populated by prior :func:`discover_projects` or
    :func:`seed_project_index` calls; if *project_id* is not known we
    trigger a rediscovery before giving up. That means a freshly created
    project shows up without waiting for the 60s cache TTL.

    Raises
    ------
    KeyError
        If no project with this id has been discovered.
    """
    from tripwire.core.store import load_project

    project_dir = get_project_dir(project_id)
    if project_dir is None:
        if not _pinned:
            # Force a rescan — useful when a new project appeared since the
            # cache was populated. Cheap enough to run on the unhappy path.
            reload_project_index()
            discover_projects(load_user_config())
            project_dir = get_project_dir(project_id)
        if project_dir is None:
            raise KeyError(project_id)

    config = load_project(project_dir)

    # model_dump so new ProjectConfig fields flow through without a manual
    # whitelist per field. The DTO fields we expose are a subset; the rest
    # live in model metadata and can be surfaced later without schema change.
    config_data: dict[str, Any] = config.model_dump(mode="json")

    return ProjectDetail(
        id=_project_id(project_dir),
        name=config.name,
        key_prefix=config.key_prefix,
        dir=str(project_dir),
        phase=config.phase.value,
        issue_count=_count_issues(project_dir),
        node_count=_count_nodes(project_dir),
        session_count=_count_sessions(project_dir),
        description=config.description,
        base_branch=config.base_branch,
        environments=list(config.environments),
        repos=config_data.get("repos", {}),
        statuses=list(config.statuses),
        status_transitions=dict(config.status_transitions),
        label_categories=config_data.get("label_categories", {}),
        graph=config_data.get("graph", {}),
        orchestration=config_data.get("orchestration", {}),
        next_issue_number=config.next_issue_number,
        next_session_number=config.next_session_number,
    )
