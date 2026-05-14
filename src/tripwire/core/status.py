"""Issue-status reachability — workflow-driven (v0.13.1 / B8).

Previously this module computed reachability from
``project.yaml.status_transitions`` — a hand-rolled adjacency table. The
v0.13.1 promotion moves that contract into the ``issue-closure`` workflow
declared in ``workflow.yaml``. Reachability now consults the workflow's
declared ``instance.status_enum`` (legal status values) and its ``routes``
(legal transitions between them).

The functions retain their pre-v0.13.1 signatures so the structure
validator (``check_status_transitions``) and the UI mutation service
keep working. They now take an explicit transitions map sourced from
the workflow, which the caller builds once via
:func:`build_issue_transitions`.
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

# The implicit starting state for every issue. Projects can rename
# `planned` in their enums but the transition graph still must have a
# node that all issues are reachable from. We use the first declared
# status as the starting state if `planned` isn't present.
DEFAULT_START_STATE = "planned"

ISSUE_CLOSURE_WORKFLOW_ID = "issue-closure"


class StatusError(ValueError):
    """Raised when a status transition is invalid or unreachable."""


def build_issue_transitions(project_dir: Path) -> dict[str, list[str]]:
    """Return ``{from_status: [to_status, ...]}`` from the issue-closure workflow.

    Reads ``workflow.yaml``'s ``issue-closure`` workflow declaration and
    collapses its ``routes:`` block into the legacy adjacency-list shape
    so the rest of this module can stay route-table-shaped.

    Routes whose endpoints are boundary ports (``source:...`` /
    ``sink:...``) are skipped — they aren't status-to-status edges.
    Workflows that don't declare ``issue-closure`` yield an empty map;
    callers fall back to "every declared status is trivially reachable"
    semantics.
    """
    from tripwire.core.workflow.loader import load_workflows

    spec = load_workflows(project_dir)
    workflow = spec.workflows.get(ISSUE_CLOSURE_WORKFLOW_ID)
    if workflow is None:
        return {}
    out: dict[str, list[str]] = {}
    declared = {s.id for s in workflow.statuses}
    if workflow.instance is not None:
        declared.update(workflow.instance.status_enum)
    for status_id in declared:
        out.setdefault(status_id, [])
    for route in workflow.routes:
        if route.from_ref.startswith("source:") or route.from_ref.startswith("sink:"):
            continue
        if route.to_ref.startswith("source:") or route.to_ref.startswith("sink:"):
            continue
        out.setdefault(route.from_ref, []).append(route.to_ref)
    return out


def is_transition_allowed(
    transitions: dict[str, list[str]], from_status: str, to_status: str
) -> bool:
    """Return True if ``from_status → to_status`` is a declared transition.

    ``transitions`` is the adjacency map returned by
    :func:`build_issue_transitions`. Self-transitions are always allowed
    (idempotent no-op).
    """
    if from_status == to_status:
        return True
    allowed = transitions.get(from_status, [])
    return to_status in allowed


def reachable_statuses(
    transitions: dict[str, list[str]], *, declared_statuses: list[str] | None = None
) -> set[str]:
    """Compute the set of statuses reachable from the start state.

    Uses ``DEFAULT_START_STATE`` if it appears in ``transitions``; falls
    back to ``declared_statuses[0]`` otherwise. With an empty
    ``transitions`` map (no issue-closure workflow yet) we treat every
    declared status as trivially reachable — we can't do better with
    no graph.
    """
    if not transitions:
        return set(declared_statuses or [])

    start = (
        DEFAULT_START_STATE
        if DEFAULT_START_STATE in transitions
        else (
            (declared_statuses[0] if declared_statuses else DEFAULT_START_STATE)
            if declared_statuses
            else DEFAULT_START_STATE
        )
    )

    reachable: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in transitions.get(current, []):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    return reachable


def is_status_reachable(
    transitions: dict[str, list[str]],
    status: str,
    *,
    declared_statuses: list[str] | None = None,
) -> bool:
    """Return True if ``status`` is reachable from the start state."""
    return status in reachable_statuses(
        transitions, declared_statuses=declared_statuses
    )
