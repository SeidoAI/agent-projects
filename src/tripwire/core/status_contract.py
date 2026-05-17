"""Issue ↔ session status contract.

Single source of truth for the relationship between session statuses and
the set of issue statuses allowed for member issues at each session phase.

Three concepts pair across the issue and session enums (``planned``,
``queued``, ``executing``, ``completed``, ``abandoned``); the
``ALLOWED_ISSUE_STATES_BY_SESSION_STATE`` contract pins the legal
combinations and a sweep helper drives forward transitions.

Public surface
--------------

* ``ALLOWED_ISSUE_STATES_BY_SESSION_STATE`` — the contract table.
* ``is_issue_state_compatible_with_session_state(s, i)`` — invariant check.
* ``sweep_target_for(session_state)`` — what state member issues should
  reach when the session enters ``session_state`` (None = no sweep).
* ``sweep_issues(project_dir, session, target_session_state)`` — apply
  the sweep to every member issue, returning a :class:`SweepResult` that
  splits fully-advanced issues from partial advancements (issues that
  cleared at least one step but didn't reach the target).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tripwire.models.session import AgentSession

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PartialAdvancement:
    """An issue that advanced one or more lifecycle steps but did not
    reach the sweep target.

    The fields name exactly where the sweep stopped and why so callers
    (``tripwire session complete``, the ``sweep-issues-forward`` CLI)
    can decide whether to abort, retry, or surface the gap to the
    operator. The pre-codex sweep returned only the fully-advanced
    keys; partials were silently dropped, which let
    ``session complete`` mark the session ``completed`` while one of
    its issues was stuck at, say, ``verified``.
    """

    issue_key: str
    started_at_status: str
    reached_status: str
    failed_at_step: str
    reason: str


# --- The contract: issue states ⊆ allowed-by-session-state -------------------

# Each session state pins a range of allowed issue states for member
# issues. ``deferred`` and ``abandoned`` are always allowed:
#  * ``deferred`` — consciously-skipped issues carry forward unchanged
#    through every session phase (e.g. punted within a session).
#  * ``abandoned`` — the project.yaml transition table allows
#    `* → abandoned` from any active state, mirroring the user-facing
#    ability to drop an issue at any time. The contract must agree, or
#    `check_issue_session_status_compatibility` would falsely error
#    every time a session-member issue is abandoned mid-flight.
#
# ``verified`` session rollback to ``in_review`` is a documented session
# lifecycle path. The rolled-back session keeps its already-verified
# issues; sweep is forward-only so they stay at ``verified``. The
# contract for the ``in_review`` session state therefore admits
# ``verified`` issues (the rollback case) in addition to ``in_review``.
#
# An issue's status must be in the set keyed by its session's status.
# Validators enforce this on write; ``sweep_issues`` advances issues to
# the floor when a session transitions forward.
ALLOWED_ISSUE_STATES_BY_SESSION_STATE: dict[str, frozenset[str]] = {
    "planned": frozenset({"planned", "deferred", "abandoned"}),
    "queued": frozenset({"planned", "queued", "deferred", "abandoned"}),
    "executing": frozenset(
        {"queued", "executing", "in_review", "deferred", "abandoned"}
    ),
    "in_review": frozenset({"in_review", "verified", "deferred", "abandoned"}),
    "verified": frozenset({"verified", "deferred", "abandoned"}),
    "completed": frozenset({"completed", "abandoned", "deferred"}),
    # Frozen: paused/failed don't constrain — issues stay where they were
    # when the session hit pause/fail. We accept any canonical issue
    # state here.
    "paused": frozenset(
        {
            "planned",
            "queued",
            "executing",
            "in_review",
            "verified",
            "completed",
            "abandoned",
            "deferred",
        }
    ),
    "failed": frozenset(
        {
            "planned",
            "queued",
            "executing",
            "in_review",
            "verified",
            "completed",
            "abandoned",
            "deferred",
        }
    ),
    # When a session is abandoned, member issues outlive it and carry
    # whatever status the agent left them at — including ``completed`` if
    # they shipped via a different session.
    "abandoned": frozenset(
        {
            "planned",
            "queued",
            "executing",
            "in_review",
            "verified",
            "completed",
            "abandoned",
            "deferred",
        }
    ),
}


# --- Sweep targets: what state issues should reach when the session enters... -

# Mapping of session-state → the issue state member issues should be
# advanced TO when the session transitions into that state. None means
# "do not sweep" (entry state, frozen state, or a state where issues
# advance individually rather than en masse).
SWEEP_TARGETS: dict[str, str | None] = {
    "planned": None,
    "queued": "queued",  # promote planned → queued
    "executing": "queued",  # defensive: any planned/older issues catch up
    "in_review": "in_review",  # sweep any executing → in_review
    "verified": "verified",
    "completed": "completed",
    "paused": None,
    "failed": None,
    "abandoned": None,
}


def is_issue_state_compatible_with_session_state(
    session_state: str, issue_state: str
) -> bool:
    """Return True if ``issue_state`` is allowed while session is in ``session_state``."""
    allowed = ALLOWED_ISSUE_STATES_BY_SESSION_STATE.get(session_state)
    if allowed is None:
        # Unknown session state — be permissive rather than crash. Validator
        # surfaces the unknown state via a separate check.
        return True
    return issue_state in allowed


def sweep_target_for(session_state: str) -> str | None:
    """Return the issue state member issues sweep TO on entry to
    ``session_state``, or None if no sweep is performed."""
    return SWEEP_TARGETS.get(session_state)


# --- Lifecycle order (used to decide "is this a forward sweep?") -------------

# Linear lifecycle order for sweep direction checks. ``deferred`` and
# ``abandoned`` are off the linear path; sweeps never touch them.
_LIFECYCLE_ORDER: tuple[str, ...] = (
    "planned",
    "queued",
    "executing",
    "in_review",
    "verified",
    "completed",
)


def _lifecycle_index(state: str) -> int | None:
    """Return position of ``state`` in the linear lifecycle, or None for
    off-path states (deferred, abandoned, paused/failed)."""
    try:
        return _LIFECYCLE_ORDER.index(state)
    except ValueError:
        return None


@dataclass(frozen=True)
class SweepResult:
    """Outcome of a :func:`sweep_issues` call.

    ``changed`` — issue keys that reached the sweep target.
    ``partial`` — issues that advanced at least one step but stopped
    short of the target. Each entry names where it got to and why it
    stopped, so callers can surface the gap rather than silently
    treating the sweep as complete.

    Iteration (``for k in result``) yields the fully-advanced keys for
    backward-compatibility with the pre-codex ``list[str]`` return
    shape; ``len(result)`` likewise returns ``len(result.changed)``.
    Callers that care about partials read ``.partial`` directly.
    """

    changed: list[str] = field(default_factory=list)
    partial: list[PartialAdvancement] = field(default_factory=list)

    def __iter__(self):
        return iter(self.changed)

    def __len__(self) -> int:
        return len(self.changed)

    def __contains__(self, key: object) -> bool:
        return key in self.changed


def sweep_issues(
    project_dir: Path,
    session: AgentSession,
    target_session_state: str,
) -> SweepResult:
    """Advance member issues to the sweep target implied by
    ``target_session_state``. Returns a :class:`SweepResult` that splits
    fully-advanced issues from partial advancements.

    Skips issues that:
    - don't exist on disk (FileNotFoundError tolerated)
    - are already at-or-beyond the sweep target on the lifecycle
    - have an off-path status (deferred, abandoned)

    Used by ``session complete`` (sweeps to ``completed``) and by the
    ``sweep_issues_forward`` side-effect handler invoked from
    ``workflow.yaml`` routes.

    v0.13.2 follow-up: each step routes through ``execute_transition``
    so the issue-closure workflow's per-route gates fire. The pre-fix
    version did ``issue.status = target`` directly + ``save_issue``,
    bypassing the executor — a single-writer violation that the
    v0.13.1 regex fitness test missed because pydantic coerces a
    string assignment into the typed enum.

    v0.13.2 codex-MED: the multi-step walker stops at the first failing
    step. The pre-codex return shape dropped partial advancements
    silently — a session_complete that swept 5 issues to ``completed``
    might leave 2 of them stuck at intermediate statuses and report
    "all done" anyway. :class:`SweepResult` surfaces those stuck issues
    via ``.partial`` plus a WARNING per partial via the module logger,
    so callers and operators see the gap.
    """
    from tripwire.core.store import load_issue
    from tripwire.core.workflow.transitions import (
        TransitionError,
        execute_transition,
    )

    target = sweep_target_for(target_session_state)
    if target is None:
        return SweepResult()

    target_idx = _lifecycle_index(target)
    if target_idx is None:
        return SweepResult()

    changed: list[str] = []
    partial: list[PartialAdvancement] = []
    for issue_key in session.issues:
        try:
            issue = load_issue(project_dir, issue_key)
        except FileNotFoundError:
            continue
        started_at = str(issue.status)
        if started_at == target:
            continue
        current_idx = _lifecycle_index(started_at)
        if current_idx is None:
            # Off-path (deferred, abandoned) — leave alone.
            continue
        if current_idx >= target_idx:
            # Already at or past the target. No backslide.
            continue

        reached_status = started_at
        failed_at_step: str | None = None
        failure_reason: str | None = None
        for step_idx in range(current_idx + 1, target_idx + 1):
            step = _LIFECYCLE_ORDER[step_idx]
            try:
                result = execute_transition(
                    project_dir,
                    workflow_id="issue-closure",
                    instance_id=issue_key,
                    target_status=step,
                )
            except TransitionError as exc:
                failed_at_step = step
                failure_reason = str(exc)
                break
            if not result.ok:
                failed_at_step = step
                failure_reason = result.message or result.reason or "rejected"
                break
            reached_status = step

        if failed_at_step is None:
            changed.append(issue_key)
            continue

        if reached_status != started_at:
            entry = PartialAdvancement(
                issue_key=issue_key,
                started_at_status=started_at,
                reached_status=reached_status,
                failed_at_step=failed_at_step,
                reason=failure_reason or "",
            )
            partial.append(entry)
            log.warning(
                "sweep_issues: %s partially advanced %s → %s "
                "(failed at %s → %s: %s); target was %s",
                issue_key,
                started_at,
                reached_status,
                reached_status,
                failed_at_step,
                failure_reason,
                target,
            )
    return SweepResult(changed=changed, partial=partial)


__all__ = [
    "ALLOWED_ISSUE_STATES_BY_SESSION_STATE",
    "SWEEP_TARGETS",
    "PartialAdvancement",
    "SweepResult",
    "is_issue_state_compatible_with_session_state",
    "sweep_issues",
    "sweep_target_for",
]
