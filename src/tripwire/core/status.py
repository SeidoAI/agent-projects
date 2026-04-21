"""Status transition validation.

Each project's `project.yaml` declares which status transitions are valid
(e.g. `todo → in_progress`, `in_progress → in_review`). The validator uses
this module to check that every issue's current status is reachable from
the canonical starting state and that any proposed transition is allowed.
"""

from __future__ import annotations

from collections import deque

from tripwire.models.project import ProjectConfig

# The implicit starting state for every issue. Projects can rename
# `backlog` in their enums but the transition graph still must have a node
# that all issues are reachable from. We use the first declared status as
# the starting state if `backlog` isn't present.
DEFAULT_START_STATE = "backlog"


class StatusError(ValueError):
    """Raised when a status transition is invalid or unreachable."""


def is_transition_allowed(
    project: ProjectConfig, from_status: str, to_status: str
) -> bool:
    """Return True if `from_status → to_status` is a declared transition."""
    if from_status == to_status:
        return True
    allowed = project.status_transitions.get(from_status, [])
    return to_status in allowed


def reachable_statuses(project: ProjectConfig) -> set[str]:
    """Compute the set of statuses reachable from the project's start state.

    Uses the first declared `statuses` entry as the start (or
    `DEFAULT_START_STATE` if no statuses declared). Walks the
    `status_transitions` graph BFS-style.
    """
    if not project.status_transitions:
        # Without transitions declared, every declared status is trivially
        # "reachable" (we can't do better with no graph).
        return set(project.statuses)

    start = (
        DEFAULT_START_STATE
        if DEFAULT_START_STATE in project.status_transitions
        else (project.statuses[0] if project.statuses else DEFAULT_START_STATE)
    )

    reachable: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in project.status_transitions.get(current, []):
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    return reachable


def is_status_reachable(project: ProjectConfig, status: str) -> bool:
    """Return True if `status` is reachable from the project's start state."""
    return status in reachable_statuses(project)
