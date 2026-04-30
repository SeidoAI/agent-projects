"""Dependency + concept graph routes (KUI-29).

Two endpoints under `/api/projects/{project_id}/graph`:

    GET  /deps              dependency graph (blocked_by edges only)
    GET  /concept           full concept graph (issues + nodes + all edges)

Both return the ReactFlow-shaped payload defined by
:class:`ReactFlowGraph`. The empty-project case returns an empty graph
(200), not a 404 — matching the contract used by the frontend graph view.

`depth` is clamped to at most 10 with the header ``X-Tripwire-Clamp:
depth`` so the frontend can surface "your depth was capped" rather than
have to duplicate the clamp logic client-side.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Body, Depends, Query, Response
from pydantic import BaseModel, ConfigDict

from tripwire.ui.dependencies import ProjectContext, get_project
from tripwire.ui.routes._common import envelope_exception
from tripwire.ui.services.graph_service import (
    ReactFlowGraph,
    build_concept_graph,
    build_dependency_graph,
)

router = APIRouter(prefix="/api/projects/{project_id}/graph", tags=["graph"])

_DEPTH_MAX = 10
_FOCUS_RE = re.compile(r"^(?:[A-Z][A-Z0-9]*-\d+|[a-z][a-z0-9-]*)$")
_NODE_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")


class LayoutEntry(BaseModel):
    """One node's persisted Concept Graph position."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class ConceptLayoutResponse(BaseModel):
    """Response for `PATCH /graph/concept/layout`."""

    layouts: dict[str, LayoutEntry]


def _validate_focus(focus: str | None) -> None:
    if focus is not None and not _FOCUS_RE.match(focus):
        raise envelope_exception(
            400,
            code="graph/bad_focus",
            detail=(
                f"Focus {focus!r} is neither a valid issue key "
                f"(e.g. KUI-12) nor a node slug (e.g. user-model)."
            ),
        )


def _clamp_depth(depth: int | None, response: Response) -> int | None:
    """Return depth clamped to `_DEPTH_MAX`, tagging the response header."""
    if depth is None:
        return None
    if depth > _DEPTH_MAX:
        response.headers["X-Tripwire-Clamp"] = "depth"
        return _DEPTH_MAX
    return depth


@router.get("/deps", response_model=ReactFlowGraph)
async def get_dependency_graph(
    response: Response,
    project: ProjectContext = Depends(get_project),  # noqa: B008
    focus: str | None = Query(None),
    depth: int | None = Query(None, ge=1),
    upstream: bool = Query(False),
    downstream: bool = Query(False),
) -> ReactFlowGraph:
    _validate_focus(focus)
    effective_depth = _clamp_depth(depth, response)
    return build_dependency_graph(
        project.project_dir,
        focus=focus,
        depth=effective_depth,
        upstream=upstream,
        downstream=downstream,
    )


@router.get("/concept", response_model=ReactFlowGraph)
async def get_concept_graph(
    project: ProjectContext = Depends(get_project),  # noqa: B008
    focus: str | None = Query(None),
    upstream: bool = Query(False),
    downstream: bool = Query(False),
) -> ReactFlowGraph:
    _validate_focus(focus)
    return build_concept_graph(
        project.project_dir,
        focus=focus,
        upstream=upstream,
        downstream=downstream,
    )


@router.patch("/concept/layout", response_model=ConceptLayoutResponse)
def patch_concept_layout(
    body: dict[str, LayoutEntry] = Body(...),  # noqa: B008
    project: ProjectContext = Depends(get_project),  # noqa: B008
) -> ConceptLayoutResponse:
    """Merge a batch of `(node_id -> {x, y})` into the layout sidecar.

    One HTTP call per debounced flush replaces the per-node PATCH that
    used to write through `nodes/<id>.yaml`. The sidecar lives at
    `.tripwire/concept-layout.json` so the file watcher does not classify
    these writes as node changes — see `core/concept_layout.py`.

    Sync `def` (not `async def`) so FastAPI runs the route on its
    threadpool: the merge does sync filesystem I/O under a `flock`, and
    blocking the event loop is what made the original layout PATCH starve
    unrelated requests.
    """
    for node_id in body:
        if not _NODE_SLUG_RE.match(node_id):
            raise envelope_exception(
                400,
                code="node/bad_slug",
                detail=(
                    f"Layout key {node_id!r} is not a valid node slug "
                    f"(lowercase letter first, then alphanumerics or hyphens)."
                ),
            )

    from tripwire.core.concept_layout import merge_concept_layouts

    updates = {nid: (entry.x, entry.y) for nid, entry in body.items()}
    merged = merge_concept_layouts(project.project_dir, updates)
    return ConceptLayoutResponse(
        layouts={nid: LayoutEntry(x=x, y=y) for nid, (x, y) in merged.items()}
    )
