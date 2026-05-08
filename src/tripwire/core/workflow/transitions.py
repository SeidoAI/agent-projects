"""Workflow executor — the SOLE writer of session.status in v0.13.

A transition is a request to move a session from its current status
to a target status via a declared route in ``workflow.yaml``. The
executor:

1. Loads ``<project>/workflow.yaml``, finds the workflow.
2. Resolves the route from (current_status, target_status). No route
   declared = transition is rejected as ``transition_not_reachable``.
3. Captures a pre-state snapshot of the session (deep copy) for
   atomic rollback.
4. Runs the route's entry gate:
   a. **Tripwires** — validators listed on the route's controls.
   b. **JIT prompts** — every controls.jit_prompts must be acked.
   c. **Prompt-checks** — every controls.prompt_checks must be invoked.
   d. **Artifacts** — every required consumed artifact must exist.
5. Captures pre-values for ``route.preserve_fields``; applies
   ``route.clear_fields`` (sets to default).
6. Flips ``session.status``, bumps ``current_status_instance``, saves.
7. Runs ``route.side_effects`` in declared order. On any failure:
   - For each completed side-effect with ``idempotent=False``, calls
     ``inverse(ctx, result)`` in reverse order.
   - Restores session from the pre-state snapshot.
   - Saves session.
   - Emits ``transition.rejected``.
8. After all side-effects succeed, re-asserts preserved field values
   (defends against accidental clearing by handlers).
9. Saves session, emits ``transition.completed``, returns.

Concurrency: per-session lockfile under
``.tripwire/locks/transition-<sid>.lock`` serialises concurrent
transitions on the same session — the execute path is the single
serialization point for ``session.status`` mutations.
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
    Workflow,
    WorkflowRoute,
    WorkflowRouteControls,
    WorkflowSpec,
    WorkflowStatus,
)
from tripwire.models.enums import SessionStatus
from tripwire.models.session import AgentSession

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


def execute_transition(
    project_dir: Path,
    *,
    session_id: str,
    target_status: str,
    flags: dict | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    """Run the gate, apply the transition, fire side-effects.

    Always emits ``transition.requested`` first, then either
    ``transition.completed`` (pass) or ``transition.rejected`` (fail).
    Raises :class:`TransitionError` for input errors that don't
    correspond to a gate verdict (unknown session / status).

    ``flags`` carries caller-local options (e.g. ``reset_acks: True``
    for the reopen route, ``reason: "..."`` for audit log entries).
    Handed to every side-effect via :class:`SideEffectContext`.
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
                workflow=workflow,
                current=current,
                current_status=current_status,
                target_status=target_status,
                statuses_by_id=statuses_by_id,
                when=when,
                flags=dict(flags or {}),
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
    workflow: Workflow,
    current,
    current_status: str,
    target_status: str,
    statuses_by_id: dict[str, WorkflowStatus],
    when: datetime,
    flags: dict,
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
    route = _route_between(workflow, current_status, target_status)
    if route is None:
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"transition_not_reachable: cannot move from "
            f"{current_status!r} to {target_status!r} via declared workflow route",
        )

    target = statuses_by_id[target_status]
    controls = _controls_for_transition(route, target)

    # 2. Tripwires — target-status entry gate from workflow.yaml.
    from tripwire.cli.transition import validate_project

    report = validate_project(
        project_dir,
        strict=True,
        fix=False,
        session_id=session_id,
        validator_ids=controls.tripwires,
        workflow=WORKFLOW_ID,
        status=target_status,
    )
    if report.errors:
        first = report.errors[0]
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"tripwires_failed: {first.code}: {first.message}",
        )

    # 3. JIT prompts — target-status entry gate from workflow.yaml.
    jit_prompt_ids = list(controls.jit_prompts)
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
    required_pcs = list(controls.prompt_checks)
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
        project_dir,
        session_id=session_id,
        target=target,
        session=session,
    )
    if missing_artifacts:
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=f"artifacts_missing: {missing_artifacts}",
        )

    # 6. Capture pre-state for atomic rollback.
    snapshot = session.model_copy(deep=True)
    preserved: dict[str, object] = {
        path: _read_path(session, path) for path in route.preserve_fields
    }

    # 7. Apply clear_fields (set declared paths to None).
    for path in route.clear_fields:
        _write_path(session, path, None)

    # 8. Flip status, assign status-instance id, save.
    n = _next_status_instance_n(project_dir, WORKFLOW_ID, session_id, target_status)
    status_instance = f"{WORKFLOW_ID}:{session_id}:{target_status}:{n}"
    session.status = SessionStatus(target_status)
    session.current_status_instance = status_instance
    session.updated_at = when
    save_session(project_dir, session)

    # 9. Run side-effects in declared order, with rollback on any failure.
    completed_effects: list[tuple[object, object]] = []
    try:
        for effect_id in route.side_effects:
            from tripwire.core.workflow.side_effects import (
                SideEffectContext,
                SideEffectFailure,
            )
            from tripwire.core.workflow.side_effects import (
                get as _get_effect,
            )

            effect = _get_effect(effect_id)
            if effect is None:
                # Unknown side-effect at runtime — should have been caught
                # by `workflow/unknown_side_effect` lint at load. Treat as
                # a hard failure rather than skip.
                raise SideEffectFailure(f"unregistered_side_effect: {effect_id!r}")
            ctx = SideEffectContext(
                project_dir=project_dir,
                session=session,
                route=route,
                flags={"from_status": current_status, **flags},
            )
            result = effect.apply(ctx)
            completed_effects.append((effect, result))
    except Exception as exc:
        from tripwire.core.workflow.side_effects import SideEffectFailure

        reason_code = (
            str(exc)
            if isinstance(exc, SideEffectFailure)
            else f"side_effect_error: {exc}"
        )
        _rollback_side_effects(
            project_dir, session_id, completed_effects, route=route, session=session
        )
        # Restore session to pre-state snapshot and persist.
        save_session(project_dir, snapshot)
        return _reject(
            project_dir,
            session_id,
            target_status,
            reason=reason_code,
        )

    # 10. Re-assert preserved fields against accidental clearing.
    for path, prior_value in preserved.items():
        current_value = _read_path(session, path)
        if current_value != prior_value:
            _write_path(session, path, prior_value)
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


def _rollback_side_effects(
    project_dir: Path,
    session_id: str,
    completed_effects: list[tuple[object, object]],
    *,
    route,
    session,
) -> None:
    """Walk completed side-effects in reverse, calling each non-idempotent
    handler's inverse. Idempotent handlers (best-effort, gh-bound, fs
    deletion) are skipped — their effects can't be cleanly undone.
    """
    from tripwire.core.workflow.side_effects import SideEffectContext

    for effect, result in reversed(completed_effects):
        if effect.idempotent or effect.inverse is None:
            continue
        ctx = SideEffectContext(
            project_dir=project_dir,
            session=session,
            route=route,
            flags={},
        )
        try:
            effect.inverse(ctx, result)
        except Exception:
            logger.exception(
                "rollback inverse failed for side-effect %r in session %s; "
                "continuing to roll back others",
                effect.id,
                session_id,
            )


def _read_path(obj: object, path: str) -> object | None:
    """Walk a dot-path on a Pydantic-or-attribute object. ``None`` if
    any segment is missing."""
    cur: object | None = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def _write_path(obj: object, path: str, value: object) -> bool:
    """Write a value to the leaf of a dot-path. Returns False if any
    intermediate segment is missing (no-op then)."""
    parts = path.split(".")
    cur: object | None = obj
    for part in parts[:-1]:
        if cur is None:
            return False
        cur = getattr(cur, part, None)
    if cur is None:
        return False
    try:
        setattr(cur, parts[-1], value)
    except (AttributeError, TypeError):
        return False
    return True


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


def _route_between(
    workflow: Workflow, current_status: str, target_status: str
) -> WorkflowRoute | None:
    for route in workflow.routes:
        if route.from_ref == current_status and route.to_ref == target_status:
            return route
    return None


def _controls_for_transition(
    route: WorkflowRoute | None, target: WorkflowStatus
) -> WorkflowRouteControls:
    if route is None:
        return WorkflowRouteControls(
            tripwires=list(target.tripwires),
            heuristics=list(target.heuristics),
            jit_prompts=list(target.jit_prompts),
            prompt_checks=list(target.prompt_checks),
        )
    return route.controls


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


class _SafeFormatDict(dict):
    """``str.format_map`` companion that leaves unknown ``{name}``
    placeholders intact instead of raising ``KeyError``.
    """

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _missing_consumed_artifacts(
    project_dir: Path,
    *,
    session_id: str,
    target: WorkflowStatus,
    session: AgentSession | None = None,
) -> list[str]:
    """Return workflow-declared consumed artifact paths that do not exist.

    Path templates can carry placeholders beyond ``{session_id}`` (e.g.
    ``{issue_key}``, ``{nnn}``, ``{yyyy-mm-dd}``). The first is
    resolvable from the session's bound issue; the latter two only
    settle at write-time. Use a name-blind safe formatter that leaves
    unknowns in place, then skip any path still carrying ``{...}``
    after the substitution — there's no way to know whether such a
    file exists, and the gate must not crash mid-transition for a
    template the runtime can't fully resolve yet.
    """
    context: dict[str, str] = {"session_id": session_id}
    if session is not None and session.issues:
        # The session's first issue key is the canonical binding for
        # `{issue_key}` template paths. If the session is bound to
        # multiple issues, additional issue artifacts surface through
        # the per-issue paths declared elsewhere.
        context["issue_key"] = session.issues[0]
    safe = _SafeFormatDict(context)

    missing: list[str] = []
    for artifact in target.artifacts.consumes:
        if not artifact.path:
            continue
        rel = artifact.path.format_map(safe)
        if "{" in rel:
            # An unresolved placeholder remains (e.g. `{nnn}` or
            # `{yyyy-mm-dd}` — settled at write-time). Cannot answer
            # "does the file exist" for such a template at gate-check;
            # skip rather than crash.
            continue
        if not (project_dir / rel).exists():
            missing.append(rel)
    return missing


__all__ = [
    "WORKFLOW_ID",
    "TransitionError",
    "TransitionResult",
    "execute_transition",
]
