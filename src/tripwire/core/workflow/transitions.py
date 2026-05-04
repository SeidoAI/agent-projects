"""Transition-token runtime — the workflow gate runner (KUI-159).

A transition is a request to move a session from its current status
to a target status. The runtime:

1. Loads ``<project>/workflow.yaml``, finds the workflow the session
   belongs to (``coding-session`` for v0.9; future workflows look up
   by ``trigger:`` against the spawn event).
2. Verifies the target status is reachable from the current status
   (single-id ``next:`` matches, or one of the conditional branches
   resolves to it).
3. Runs the target-status entry gate from ``workflow.yaml``:

   a. **Validators** — run only the validators listed on the target
      status with ``strict=True``. Any error fails the gate.
   b. **JIT prompts** — for every JIT prompt listed on the target
      status, confirm :meth:`JitPrompt.is_acknowledged` returns True.
      An unack'd blocking JIT prompt fails the gate.
   c. **Prompt-checks** — for every prompt-check listed on the target
      status, query the events log to verify it was invoked before
      entering that status.
   d. **Artifacts** — required consumed artifacts with concrete paths
      must exist before entering the target status.

4. On pass: session.status = target, ``current_status_instance``
   bumped, ``transition.completed`` emitted.
5. On fail: ``transition.rejected`` emitted with a structured
   ``reason``; session stays put.

Concurrency: per-session lockfile under
``.tripwire/locks/transition-<sid>.lock`` serialises concurrent
transitions on the same session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tripwire.core.events.log import emit_event, read_events
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.session_store import load_session, save_session
from tripwire.core.workflow.loader import load_workflows
from tripwire.core.workflow.schema import (
    NextSpec,
    Workflow,
    WorkflowSpec,
    WorkflowStatus,
)
from tripwire.models.enums import SessionStatus

logger = logging.getLogger(__name__)


WORKFLOW_ID = "coding-session"


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of one transition request."""

    ok: bool
    reason: str | None  # structured reason code; None on pass
    message: str | None  # human-readable detail
    status_instance: str | None  # `{workflow}:{instance}:{status}:{n}` on pass


class TransitionError(Exception):
    """Raised for unrecoverable input errors (unknown session/status)."""


def _isoformat_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_workflow(spec: WorkflowSpec) -> Workflow:
    """Return the canonical workflow for v0.9 — only ``coding-session``
    is materialised. Raises :class:`TransitionError` if missing."""
    wf = spec.workflows.get(WORKFLOW_ID)
    if wf is None:
        raise TransitionError(
            f"workflow {WORKFLOW_ID!r} is not declared in workflow.yaml"
        )
    return wf


def _is_reachable(current: str, target: str, next_spec: NextSpec) -> bool:
    """True iff ``target`` is reachable from ``current`` via ``next_spec``."""
    if next_spec.kind == "single":
        return next_spec.single == target
    if next_spec.kind == "conditional":
        if next_spec.conditional is None:
            return False
        # Equality predicates are evaluated against an empty context
        # for now — the runtime context is built by the gate runner
        # later. We accept any branch whose `then` matches the target
        # since reachability ≠ what-actually-happens-at-runtime.
        return any(branch.then == target for branch in next_spec.conditional)
    return False  # terminal — nothing reachable


def _next_status_instance_n(
    project_dir: Path, workflow: str, instance: str, status: str
) -> int:
    """Count prior `transition.completed` events for this status and
    return n+1, where n is the number of prior visits."""
    n = 0
    for row in read_events(
        project_dir,
        workflow=workflow,
        instance=instance,
        event="transition.completed",
    ):
        details = row.get("details") or {}
        if details.get("to_status") == status:
            n += 1
    return n + 1


def request_transition(
    project_dir: Path,
    *,
    session_id: str,
    target_status: str,
    now: datetime | None = None,
) -> TransitionResult:
    """Run the gate and apply the transition.

    Always emits ``transition.requested`` first, then either
    ``transition.completed`` (pass) or ``transition.rejected`` (fail).
    Raises :class:`TransitionError` for input errors that don't
    correspond to a gate verdict (unknown session / status).
    """
    when = now or datetime.now(tz=timezone.utc)

    spec = load_workflows(project_dir)
    workflow = _resolve_workflow(spec)
    statuses_by_id = workflow.statuses_by_id
    if target_status not in statuses_by_id:
        raise TransitionError(
            f"unknown status {target_status!r} in workflow {WORKFLOW_ID!r}; "
            f"valid statuses: {sorted(statuses_by_id)}"
        )

    # Pre-lock load: just to populate `transition.requested`'s
    # `from_status` field with the caller's perspective. The gate
    # body re-loads inside the lock to evaluate against fresh state
    # (see codex P1 on PR #73 — concurrent transitions could otherwise
    # both validate against the same stale snapshot).
    try:
        pre_lock_session = load_session(project_dir, session_id)
    except FileNotFoundError as exc:
        raise TransitionError(f"session {session_id!r} not found") from exc

    pre_lock_status = pre_lock_session.status.value

    # Always emit `transition.requested` first.
    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        status=target_status,
        event="transition.requested",
        details={"from_status": pre_lock_status, "to_status": target_status},
        now=when,
    )

    lock_name = f".tripwire/locks/transition-{session_id}.lock"
    try:
        with project_lock(project_dir, name=lock_name):
            # Re-read session state INSIDE the lock — stale snapshots
            # before the lock could let two concurrent transitions
            # validate against the same source status and both emit
            # `transition.completed`. Fresh read here is the
            # serialization point.
            session = load_session(project_dir, session_id)
            current_status = session.status.value
            current = statuses_by_id.get(current_status)
            return _run_gate(
                project_dir,
                session=session,
                current=current,
                current_status=current_status,
                target_status=target_status,
                statuses_by_id=statuses_by_id,
                when=when,
            )
    except LockTimeout as exc:
        result = TransitionResult(
            ok=False,
            reason="lock_timeout",
            message=str(exc),
            status_instance=None,
        )
        emit_event(
            project_dir,
            workflow=WORKFLOW_ID,
            instance=session_id,
            status=target_status,
            event="transition.rejected",
            details={"reason": result.reason, "message": result.message},
            now=datetime.now(tz=timezone.utc),
        )
        return result


def _run_gate(
    project_dir: Path,
    *,
    session,
    current,
    current_status: str,
    target_status: str,
    statuses_by_id: dict[str, WorkflowStatus],
    when: datetime,
) -> TransitionResult:
    """The gate body. Caller holds the per-session transition lock."""
    session_id = session.id
    # 1. Reachability.
    if current is None:
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"transition_not_reachable: current status "
            f"{current_status!r} is not declared in workflow.yaml",
        )
    if not _is_reachable(current_status, target_status, current.next):
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"transition_not_reachable: cannot move from "
            f"{current_status!r} to {target_status!r} via declared `next:`",
        )

    target = statuses_by_id[target_status]

    # 2. Validators — target-status entry gate from workflow.yaml.
    from tripwire.cli.transition import validate_project

    report = validate_project(
        project_dir,
        strict=True,
        fix=False,
        session_id=session_id,
        validator_ids=target.validators,
        workflow=WORKFLOW_ID,
        status=target_status,
    )
    if report.errors:
        first = report.errors[0]
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"validators_failed: {first.code}: {first.message}",
        )

    # 3. JIT prompts — target-status entry gate from workflow.yaml.
    jit_prompt_ids = list(target.jit_prompts)
    if jit_prompt_ids:
        from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry

        registry = load_jit_prompt_registry(project_dir)
        unacked = _unacked_status_jit_prompts(
            project_dir, registry, session_id=session_id, want_ids=set(jit_prompt_ids)
        )
        if unacked:
            return _reject(
                project_dir,
                session_id,
                target_status,
                reason=f"jit_prompts_not_acknowledged: {sorted(unacked)}",
            )

    # 4. Prompt-checks — target-status entry gate from workflow.yaml.
    required_pcs = list(target.prompt_checks)
    if required_pcs:
        invoked = _invoked_prompt_checks_at_status(
            project_dir, instance=session_id, status=target_status
        )
        missing = [pc for pc in required_pcs if pc not in invoked]
        if missing:
            return _reject(
                project_dir,
                session_id,
                target_status,
                reason=f"prompt_checks_missing: {missing}",
            )

    # 5. Artifacts — target-status consumed paths must exist.
    missing_artifacts = _missing_consumed_artifacts(
        project_dir, session_id=session_id, target=target
    )
    if missing_artifacts:
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"artifacts_missing: {missing_artifacts}",
        )

    # 6. Pass — assign status-instance id, save session, emit completed.
    n = _next_status_instance_n(project_dir, WORKFLOW_ID, session_id, target_status)
    status_instance = f"{WORKFLOW_ID}:{session_id}:{target_status}:{n}"
    session.status = SessionStatus(target_status)
    session.current_status_instance = status_instance
    session.updated_at = when
    save_session(project_dir, session)

    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        status=target_status,
        event="transition.completed",
        details={
            "from_status": current_status,
            "to_status": target_status,
            "status_instance": status_instance,
        },
        now=datetime.now(tz=timezone.utc),
    )
    return TransitionResult(
        ok=True,
        reason=None,
        message=None,
        status_instance=status_instance,
    )


def _reject(
    project_dir: Path,
    session_id: str,
    target_status: str,
    *,
    reason: str,
) -> TransitionResult:
    emit_event(
        project_dir,
        workflow=WORKFLOW_ID,
        instance=session_id,
        status=target_status,
        event="transition.rejected",
        details={"reason": reason},
    )
    return TransitionResult(
        ok=False,
        reason=reason.split(":", 1)[0],
        message=reason,
        status_instance=None,
    )


def _unacked_status_jit_prompts(
    project_dir: Path,
    registry: dict,
    *,
    session_id: str,
    want_ids: set[str],
) -> set[str]:
    """Return the subset of ``want_ids`` whose JIT prompt is not
    acknowledged for the session.

    The JIT prompt registry is keyed by `fires_on` event; we walk it,
    find each instance whose id is in ``want_ids``, build a
    :class:`JitPromptContext`, and ask
    :meth:`JitPrompt.is_acknowledged`. Missing prompts (in the want
    set but not loaded) count as unacked — the gate is conservative.
    """
    from tripwire._internal.jit_prompts import JitPromptContext
    from tripwire.core.store import load_project

    project = load_project(project_dir)
    project_id = project.name.lower().replace(" ", "-")
    ctx = JitPromptContext(
        project_dir=project_dir, session_id=session_id, project_id=project_id
    )
    unacked = set(want_ids)
    for instances in registry.values():
        for jit_prompt in instances:
            if jit_prompt.id in unacked and jit_prompt.is_acknowledged(ctx):
                unacked.discard(jit_prompt.id)
    return unacked


def _invoked_prompt_checks_at_status(
    project_dir: Path, *, instance: str, status: str
) -> set[str]:
    """Return prompt-check ids invoked for ``instance`` at ``status``
    since the session entered the status — derived by walking the
    events log for `prompt_check.invoked` events filtered by
    instance/status."""
    invoked: set[str] = set()
    for row in read_events(
        project_dir,
        instance=instance,
        status=status,
        event="prompt_check.invoked",
    ):
        details = row.get("details") or {}
        pc_id = details.get("id")
        if isinstance(pc_id, str):
            invoked.add(pc_id)
    return invoked


def _missing_consumed_artifacts(
    project_dir: Path, *, session_id: str, target: WorkflowStatus
) -> list[str]:
    """Return workflow-declared consumed artifact paths that do not exist."""
    missing: list[str] = []
    for artifact in target.artifacts.consumes:
        if not artifact.path:
            continue
        rel = artifact.path.format(session_id=session_id)
        if not (project_dir / rel).exists():
            missing.append(rel)
    return missing


__all__ = [
    "WORKFLOW_ID",
    "TransitionError",
    "TransitionResult",
    "request_transition",
]
