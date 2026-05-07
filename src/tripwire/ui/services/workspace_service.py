"""Workspace auto-discovery service.

Walks ``config.workspace_roots`` looking for ``workspace.yaml`` markers
and returns lightweight summaries. The 60s in-memory cache mirrors
``project_service`` to absorb route hits.

Surfaces enough data for the v0.10.0 UI workspace switcher:

* ``GET /api/workspaces`` returns ``WorkspaceSummary[]``
* Project listings carry a ``workspace_id`` so the client can group
  projects under the workspace headings without a second round-trip.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tripwire.core.workspace_store import load_workspace
from tripwire.ui.config import UserConfig, load_user_config

logger = logging.getLogger("tripwire.ui.services.workspace_service")

_CACHE_TTL_SECONDS = 60


class WorkspaceSummary(BaseModel):
    """Lightweight workspace descriptor for the picker dropdown."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    name: str
    slug: str
    dir: str
    description: str = ""
    project_slugs: list[str]


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_discovery_cache: tuple[float, list[WorkspaceSummary]] | None = None
_workspace_dirs_by_id: dict[str, Path] = {}


def _workspace_id(abs_dir: Path) -> str:
    """Stable, opaque id derived from the workspace dir path.

    Mirrors ``_project_id`` so the front-end can treat workspace + project
    ids interchangeably as opaque strings.
    """
    return hashlib.blake2s(f"workspace:{abs_dir}".encode(), digest_size=6).hexdigest()


def _try_load_workspace_summary(abs_dir: Path) -> WorkspaceSummary | None:
    """Best-effort load of a workspace summary from *abs_dir*.

    Returns ``None`` and logs a warning on any failure (parse error,
    schema mismatch, IO, etc.) so a single bad workspace doesn't take
    discovery down.
    """
    try:
        ws = load_workspace(abs_dir)
    except Exception as exc:
        logger.warning("Skipping workspace %s: %s", abs_dir, exc)
        return None

    return WorkspaceSummary(
        id=_workspace_id(abs_dir),
        name=ws.name,
        slug=ws.slug,
        dir=str(abs_dir),
        description=ws.description or "",
        project_slugs=[p.slug for p in ws.projects],
    )


def _find_workspaces_in_root(root: Path, max_depth: int) -> list[Path]:
    """Walk *root* up to *max_depth* levels looking for ``workspace.yaml``.

    Same shape as :func:`project_service._find_projects_in_root` but with
    a different marker file. Reusing the project-side helper isn't
    straightforward because that one is hard-coded to ``project.yaml``.
    """
    found: list[Path] = []
    if not root.is_dir():
        return found

    if (root / "workspace.yaml").is_file():
        found.append(root)

    if max_depth < 2:
        return found

    try:
        children = sorted(root.iterdir())
    except PermissionError:
        return found

    for child in children:
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in {
            ".git",
            ".venv",
            "node_modules",
            "__pycache__",
        }:
            continue
        if (child / "workspace.yaml").is_file():
            found.append(child)
    return found


def discover_workspaces(config: UserConfig) -> list[WorkspaceSummary]:
    """Discover workspaces under ``config.workspace_roots``.

    Cached for 60s like ``discover_projects``. No CWD probe and no
    fallback locations — workspaces are an explicit-registration
    concept; ``project.yaml``'s ``workspace.path`` pointer can still
    surface a workspace project-side even if the workspace itself
    isn't registered as a discovery root.
    """
    global _discovery_cache, _workspace_dirs_by_id

    now = time.monotonic()
    if _discovery_cache is not None:
        cached_at, cached_results = _discovery_cache
        if now - cached_at < _CACHE_TTL_SECONDS:
            return cached_results

    seen: set[Path] = set()
    candidates: list[Path] = []
    for root in config.workspace_roots:
        for candidate in _find_workspaces_in_root(root, max_depth=2):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)

    summaries: list[WorkspaceSummary] = []
    for ws_dir in candidates:
        summary = _try_load_workspace_summary(ws_dir)
        if summary is not None:
            summaries.append(summary)

    _discovery_cache = (now, summaries)
    _workspace_dirs_by_id = {s.id: Path(s.dir) for s in summaries}
    return summaries


def reload_workspace_index() -> None:
    """Clear the discovery cache so the next call rescans."""
    global _discovery_cache, _workspace_dirs_by_id
    _discovery_cache = None
    _workspace_dirs_by_id = {}


def list_workspaces() -> list[WorkspaceSummary]:
    """Return every discovered workspace as a :class:`WorkspaceSummary`.

    Loads the user config lazily on each call — cheap, and the in-memory
    discovery cache (60s TTL) absorbs repeated route hits.
    """
    return discover_workspaces(load_user_config())


def get_workspace_dir(workspace_id: str) -> Path | None:
    """Return the directory for *workspace_id*, or ``None`` if unknown."""
    return _workspace_dirs_by_id.get(workspace_id)


def get_workspace_id_for_project(
    project_dir: Path, workspace_pointer: str
) -> str | None:
    """Resolve a project's ``workspace.path`` pointer to a workspace id.

    Returns ``None`` when the pointer doesn't resolve to a known
    workspace — either because the dir doesn't exist, doesn't have a
    ``workspace.yaml``, or because the workspace isn't under any
    registered ``workspace_roots``. Returning a value the picker can't
    name back gives the user an "Unknown workspace" group with no
    escape; gating on registration makes the project land in
    "Unworkspaced" instead, which is accurate and recoverable via
    ``tripwire config add workspace-root <path>``.

    Used by :func:`project_service._try_load_summary` to populate
    ``ProjectSummary.workspace_id``.
    """
    try:
        target = (project_dir / workspace_pointer).resolve()
    except OSError:
        return None
    if not (target / "workspace.yaml").is_file():
        return None

    # Lazily populate the index so this works on the first request after
    # process start (before any /api/workspaces hit).
    if not _workspace_dirs_by_id:
        discover_workspaces(load_user_config())

    candidate = _workspace_id(target)
    return candidate if candidate in _workspace_dirs_by_id else None


__all__ = [
    "WorkspaceSummary",
    "discover_workspaces",
    "get_workspace_dir",
    "get_workspace_id_for_project",
    "list_workspaces",
    "reload_workspace_index",
]
