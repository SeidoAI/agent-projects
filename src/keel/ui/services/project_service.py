"""Project auto-discovery service.

Scans the filesystem for ``project.yaml`` files and returns lightweight
summaries. Results are cached for 60 seconds; call ``reload_project_index()``
to force a rescan.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from pydantic import BaseModel

from keel.ui.config import UserConfig

logger = logging.getLogger("keel.ui.services.project_service")

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

    id: str
    name: str
    key_prefix: str
    dir: str
    phase: str
    issue_count: int
    node_count: int
    session_count: int


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_discovery_cache: tuple[float, list[ProjectSummary]] | None = None
_project_index: dict[str, Path] = {}


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
    from keel.core.store import load_project

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
    """Discover keel projects and return their summaries.

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

    # Build summaries
    summaries: list[ProjectSummary] = []
    index: dict[str, Path] = {}
    for project_dir in candidates:
        summary = _try_load_summary(project_dir)
        if summary is not None:
            summaries.append(summary)
            index[summary.id] = project_dir

    _discovery_cache = (now, summaries)
    _project_index = index
    return summaries


def get_project_dir(project_id: str) -> Path | None:
    """Return the directory for *project_id*, or ``None`` if unknown."""
    return _project_index.get(project_id)


def seed_project_index(project_dirs: list[Path]) -> None:
    """Populate the project index from an explicit list of directories.

    Used by ``start_server`` when the CLI's ``--project-dir`` flag bypasses
    ``discover_projects()``, which is the normal path that populates the index.
    """
    global _project_index
    for d in project_dirs:
        resolved = d.resolve()
        _project_index[_project_id(resolved)] = resolved


def reload_project_index() -> None:
    """Clear the discovery cache so the next call rescans."""
    global _discovery_cache, _project_index
    _discovery_cache = None
    _project_index = {}
