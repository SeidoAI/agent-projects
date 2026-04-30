"""Concept-node routes (KUI-28).

Four endpoints under `/api/projects/{project_id}`:

    GET   /nodes                         list (filters)
    GET   /nodes/{node_id}                single detail
    POST  /nodes/check                    full freshness report
    GET   /refs/reverse/{node_id}         who references this node

Note the reverse-refs endpoint sits under `/refs/reverse/{node_id}`,
not `/nodes/{node_id}/refs` — the API contract put it that way and the
frontend matches. We declare a single router with the
`/api/projects/{project_id}` prefix so both path shapes share the
`project_id` dependency and tag grouping.

Concept Graph layout persistence (KUI-104) used to live here as
``PATCH /nodes/{id}/layout``. It moved to a project-scoped sidecar
batched at ``PATCH /graph/concept/layout`` — see ``routes/graph.py``
and ``core/concept_layout.py``.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.node_service import (
    FreshnessReport,
    NodeDetail,
    NodeSummary,
    ReverseRefsResult,
    check_all_freshness,
)
from tripwire.ui.services.node_service import (
    get_node as svc_get_node,
)
from tripwire.ui.services.node_service import (
    list_nodes as svc_list_nodes,
)
from tripwire.ui.services.node_service import (
    reverse_refs as svc_reverse_refs,
)

router = APIRouter(prefix="/api/projects/{project_id}", tags=["nodes"])

_SLUG_PATTERN = r"^[a-z][a-z0-9-]*$"
_SLUG_RE = re.compile(_SLUG_PATTERN)


def _ensure_slug(node_id: str) -> None:
    if not _SLUG_RE.match(node_id):
        raise envelope_exception(
            400,
            code="node/bad_slug",
            detail=(
                f"Node id {node_id!r} does not match {_SLUG_PATTERN} "
                "(lowercase letter first, then alphanumerics or hyphens)."
            ),
        )


@router.get("/nodes", response_model=list[NodeSummary])
async def list_nodes(
    project: ProjectContext = Depends(get_project),  # noqa: B008
    type: str | None = Query(None, description="Filter by node type"),
    status: str | None = Query(None, description="Filter by node status"),
    stale: bool | None = Query(None, description="Filter by freshness"),
) -> list[NodeSummary]:
    return svc_list_nodes(
        project.project_dir, node_type=type, status=status, stale=stale
    )


@router.post("/nodes/check", response_model=FreshnessReport)
async def check_freshness(
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> FreshnessReport:
    """Full freshness sweep — read-only, synchronous."""
    return check_all_freshness(project.project_dir)


@router.get("/nodes/{node_id}", response_model=NodeDetail)
async def get_node(
    node_id: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> NodeDetail:
    _ensure_slug(node_id)
    try:
        return svc_get_node(project.project_dir, node_id)
    except ValueError as exc:
        raise envelope_exception(400, code="node/bad_slug", detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise envelope_exception(
            404,
            code="node/not_found",
            detail=f"Node {node_id!r} not found in this project.",
        ) from exc


@router.get("/refs/reverse/{node_id}", response_model=ReverseRefsResult)
async def reverse_refs(
    node_id: str,
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ReverseRefsResult:
    _ensure_slug(node_id)
    try:
        return svc_reverse_refs(project.project_dir, node_id)
    except ValueError as exc:
        raise envelope_exception(400, code="node/bad_slug", detail=str(exc)) from exc
