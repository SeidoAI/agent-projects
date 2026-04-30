"""Concept-node read service — list, detail, freshness, reverse refs.

Wraps :mod:`tripwire.core.node_store`, :mod:`tripwire.core.freshness`, and
:mod:`tripwire.core.graph_cache` to produce API-shaped models for the
``/api/projects/{pid}/nodes`` routes.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tripwire.core import graph_cache
from tripwire.core.freshness import check_node_freshness
from tripwire.core.node_store import list_nodes as _core_list_nodes
from tripwire.core.node_store import load_node
from tripwire.core.store import ProjectNotFoundError, load_project
from tripwire.models.graph import FreshnessStatus
from tripwire.models.node import NODE_ID_PATTERN

logger = logging.getLogger("tripwire.ui.services.node_service")


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


NodeFreshnessStatus = Literal["current", "stale", "source_missing"]


class NodeSource(BaseModel):
    """A node's source pointer, flattened for the DTO layer."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    repo: str
    path: str
    lines: tuple[int, int] | None = None
    branch: str | None = None
    content_hash: str | None = None


class NodeLayout(BaseModel):
    """Persisted (x, y) layout, mirrored from the YAML model layer."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    x: float
    y: float


class NodeSummary(BaseModel):
    """Lightweight node descriptor for list views."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    type: str
    name: str
    description: str | None = None
    status: str
    tags: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    ref_count: int = 0
    layout: NodeLayout | None = None


class NodeDetail(NodeSummary):
    """Full node detail — summary fields plus body, source, is_stale."""

    body: str = ""
    source: NodeSource | None = None
    is_stale: bool = False


class FreshnessEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    status: NodeFreshnessStatus


class FreshnessReport(BaseModel):
    """Result of :func:`check_all_freshness`."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    nodes: list[FreshnessEntry] = Field(default_factory=list)


ReferrerKind = Literal["issue", "node", "session"]


class Referrer(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    id: str
    kind: ReferrerKind


class ReverseRefsResult(BaseModel):
    """Result of :func:`reverse_refs` — who references this node."""

    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    node_id: str
    referrers: list[Referrer] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Match IDs that look like issue keys: PREFIX-NUMBER (e.g. KUI-14).
_ISSUE_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


def _require_valid_id(node_id: str) -> None:
    """Raise ValueError if *node_id* doesn't match the node slug rule.

    Prevents path-traversal (e.g. ``../secret``) and keeps every callsite
    (list filters, get, freshness, reverse_refs) consistent.
    """
    if not NODE_ID_PATTERN.match(node_id):
        raise ValueError(
            f"Invalid node id {node_id!r} — must match {NODE_ID_PATTERN.pattern}"
        )


def _classify_referrer(ref_id: str) -> ReferrerKind:
    """Classify a referrer id as issue / node / session.

    Sessions and nodes both use slug ids, so we can't tell them apart
    from the id alone. The graph cache's `referenced_by` currently only
    contains issue and node ids (sessions don't produce edges), so every
    slug-shaped id is a node.
    """
    if _ISSUE_ID_RE.match(ref_id):
        return "issue"
    return "node"


def _scan_reverse_refs(project_dir: Path, node_id: str) -> list[str]:
    """Scan issue + node files for `[[node_id]]` references.

    Last-resort fallback when the graph cache is missing AND a rebuild
    attempt also failed. Reads every issue and every node body and
    greps for the reference id.
    """
    from tripwire.core.reference_parser import extract_references
    from tripwire.core.store import list_issues

    referrers: list[str] = []
    for issue in list_issues(project_dir):
        if node_id in extract_references(issue.body):
            referrers.append(issue.id)
    for node in _core_list_nodes(project_dir):
        if node.id == node_id:
            continue
        if node_id in extract_references(node.body):
            referrers.append(node.id)
        elif node_id in node.related:
            referrers.append(node.id)
    return referrers


def _load_cache_ensuring_fresh(project_dir: Path):  # type: ignore[no-untyped-def]
    """Load the graph cache, building it once if absent.

    Per the KUI-16 execution constraint: *"If ``graph/index.yaml`` is
    missing, call ``tripwire.core.graph_cache.ensure_fresh(project_dir)``
    once per request — avoid infinite rebuild loops."*

    We call ``ensure_fresh`` at most once per call. If the rebuild fails
    (OSError, TimeoutError, or any other IO hazard during lock acquire)
    we log a warning and return ``None``; callers then fall back to a
    scan or empty result rather than 500-ing the route.
    """
    cache = graph_cache.load_index(project_dir)
    if cache is not None:
        return cache
    try:
        graph_cache.ensure_fresh(project_dir)
    except (OSError, TimeoutError) as exc:
        logger.warning(
            "node_service: graph cache rebuild failed for %s: %s",
            project_dir,
            exc,
        )
        return None
    return graph_cache.load_index(project_dir)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_nodes(
    project_dir: Path,
    *,
    node_type: str | None = None,
    status: str | None = None,
    stale: bool | None = None,
) -> list[NodeSummary]:
    """Return every concept node as a :class:`NodeSummary`.

    Filters:

    - ``node_type`` — exact match on the ``type`` field.
    - ``status`` — exact match on the ``status`` field.
    - ``stale=True`` — restrict to the cache's ``stale_nodes`` list.
      ``stale=False`` excludes them; ``None`` (default) means no filter.

    ``ref_count`` comes from the graph cache's ``referenced_by`` index.
    If the cache file is missing, we call ``graph_cache.ensure_fresh``
    once to build it (per KUI-16 execution constraint); if that fails
    we fall back to ``ref_count=0``. Freshness is NOT computed here —
    it's expensive — use :func:`check_all_freshness`.
    """
    cache = _load_cache_ensuring_fresh(project_dir)
    stale_set: set[str] = set(cache.stale_nodes) if cache is not None else set()
    ref_counts: dict[str, int] = {}
    if cache is not None:
        ref_counts = {k: len(v) for k, v in cache.referenced_by.items()}

    out: list[NodeSummary] = []
    for node in _core_list_nodes(project_dir):
        if node_type is not None and node.type != node_type:
            continue
        if status is not None and node.status != status:
            continue
        is_stale_node = node.id in stale_set
        if stale is True and not is_stale_node:
            continue
        if stale is False and is_stale_node:
            continue

        out.append(
            NodeSummary(
                id=node.id,
                type=node.type,
                name=node.name,
                description=node.description,
                status=node.status,
                tags=list(node.tags),
                related=list(node.related),
                ref_count=ref_counts.get(node.id, 0),
                layout=(
                    NodeLayout(x=node.layout.x, y=node.layout.y)
                    if node.layout is not None
                    else None
                ),
            )
        )
    return out


def get_node(project_dir: Path, node_id: str) -> NodeDetail:
    """Return the full :class:`NodeDetail` for *node_id*.

    Raises :class:`ValueError` on an invalid slug and :class:`FileNotFoundError`
    on a missing file.
    """
    _require_valid_id(node_id)
    node = load_node(project_dir, node_id)

    cache = _load_cache_ensuring_fresh(project_dir)
    stale_set: set[str] = set(cache.stale_nodes) if cache is not None else set()
    ref_count = len(cache.referenced_by.get(node_id, [])) if cache is not None else 0

    source: NodeSource | None = None
    if node.source is not None:
        source = NodeSource(
            repo=node.source.repo,
            path=node.source.path,
            lines=node.source.lines,
            branch=node.source.branch,
            content_hash=node.source.content_hash,
        )

    return NodeDetail(
        id=node.id,
        type=node.type,
        name=node.name,
        description=node.description,
        status=node.status,
        tags=list(node.tags),
        related=list(node.related),
        ref_count=ref_count,
        layout=(
            NodeLayout(x=node.layout.x, y=node.layout.y)
            if node.layout is not None
            else None
        ),
        body=node.body,
        source=source,
        is_stale=node.id in stale_set,
    )


def check_all_freshness(project_dir: Path) -> FreshnessReport:
    """Live freshness check across every active node with a source.

    Each node's status is one of:

    - ``current`` — content hash matches
    - ``stale`` — content hash differs (or no baseline recorded)
    - ``source_missing`` — source file could not be fetched

    Nodes without a source are omitted (they have nothing to check).
    Expensive — only called on the dedicated freshness route.
    """
    try:
        project = load_project(project_dir)
    except ProjectNotFoundError:
        # No project config means we can't resolve repo locals; skip.
        return FreshnessReport(nodes=[])

    entries: list[FreshnessEntry] = []
    for node in _core_list_nodes(project_dir):
        if node.status != "active" or node.source is None:
            continue
        result = check_node_freshness(node, project)
        if result.status == FreshnessStatus.FRESH:
            label: NodeFreshnessStatus = "current"
        elif result.status == FreshnessStatus.SOURCE_MISSING:
            label = "source_missing"
        elif result.status == FreshnessStatus.STALE:
            label = "stale"
        else:
            # NO_SOURCE — skipped above, but be defensive.
            continue
        entries.append(FreshnessEntry(id=node.id, status=label))

    return FreshnessReport(nodes=entries)


def reverse_refs(project_dir: Path, node_id: str) -> ReverseRefsResult:
    """Return every entity that references *node_id*.

    Reads ``graph/index.yaml``'s ``referenced_by`` when available. If
    the cache is missing we rebuild it once (per KUI-16 execution
    constraint); if the rebuild fails we fall back to a full
    filesystem scan.
    """
    _require_valid_id(node_id)

    cache = _load_cache_ensuring_fresh(project_dir)
    if cache is not None:
        referrer_ids = list(cache.referenced_by.get(node_id, []))
    else:
        referrer_ids = _scan_reverse_refs(project_dir, node_id)

    return ReverseRefsResult(
        node_id=node_id,
        referrers=[
            Referrer(id=rid, kind=_classify_referrer(rid)) for rid in referrer_ids
        ],
    )


__all__ = [
    "FreshnessEntry",
    "FreshnessReport",
    "NodeDetail",
    "NodeLayout",
    "NodeSource",
    "NodeSummary",
    "Referrer",
    "ReverseRefsResult",
    "check_all_freshness",
    "get_node",
    "list_nodes",
    "reverse_refs",
]
