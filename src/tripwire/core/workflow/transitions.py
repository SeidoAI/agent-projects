"""Workflow executor — the SOLE writer of ``session.status`` in v0.13.

In the v0.13 atomic-primitive model :func:`execute_transition` is a
thin commit primitive. A transition is a request to move an entity
(session today; issue / pr / pm-task tomorrow) from its current status
to a target status via a declared route in ``workflow.yaml``. The
executor:

1. Acquires a per-instance transition lock.
2. Loads ``<project>/workflow.yaml``, resolves the workflow by
   ``workflow_id``.
3. Reads fresh state inside the lock and resolves the route from
   ``(current_status, target_status)``. No route declared = transition
   is rejected as ``transition_not_reachable``.
4. Runs the route's entry gate, in order:
   a. **Tripwires** — validators listed on the route's controls.
   b. **JIT prompts** — every ``controls.jit_prompts`` must be acked.
   c. **Prompt-checks** — every ``controls.prompt_checks`` must be
      invoked since the status was entered.
   d. **Artifacts** — every required consumed artifact must exist.
5. Captures pre-values for ``route.preserve_fields``; applies
   ``route.clear_fields`` (sets the path to ``None``).
6. Flips ``session.status``, bumps ``current_status_instance``,
   saves the session.
7. Runs four best-effort post-write hooks inline (coding-session
   workflow only — other workflows get no hooks until step 7-8):
   - Close the active engagement on terminal transitions.
   - Append audit record to ``.tripwire/audit.jsonl``.
   - Append telemetry row.
   - Reset session acks when ``flags["reset_acks"]`` is set.
8. Emits ``transition.completed``, returns ``TransitionResult.ok=True``.

There is no orchestration of external side-effects (sweep issues,
rebase PT, kill runtime, etc.) — those live as Layer-1 CLI wrappers
and direct-mutation cli paths now. There is also no rollback machinery:
the gate either rejects before the write (no state mutated) or commits
the write (the four post-write hooks are best-effort and never fail
the transition).

Concurrency: per-instance lockfile under
``.tripwire/locks/transition-<sid>.lock`` serialises concurrent
transitions on the same entity — the execute path is the single
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


def _resolve_workflow(spec: WorkflowSpec, workflow_id: str) -> Workflow:
    """Return the workflow named ``workflow_id`` or raise."""
    wf = spec.workflows.get(workflow_id)
    if wf is None:
        raise TransitionError(
            f"workflow {workflow_id!r} is not declared in workflow.yaml"
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
    workflow_id: str = "coding-session",
    session_id: str | None = None,
    instance_id: str | None = None,
    target_status: str,
    flags: dict | None = None,
    now: datetime | None = None,
) -> TransitionResult:
    """Run the gate, atomically write status, fire post-write hooks.

    Always emits ``transition.requested`` first, then either
    ``transition.completed`` (pass) or ``transition.rejected`` (fail).
    Raises :class:`TransitionError` for input errors that don't
    correspond to a gate verdict (unknown workflow / session / status).

    ``workflow_id`` selects the workflow declared in ``workflow.yaml``.
    Today only ``coding-session`` materialises at runtime (the loader
    reads only ``AgentSession`` for any workflow id) — other workflow
    ids will raise ``TransitionError`` at load until step 7-8 plumbs
    them in.

    ``instance_id`` (or the legacy positional ``session_id``) names the
    entity being transitioned. For the coding-session workflow this is
    the session id.

    ``flags`` carries caller-local options:
    - ``reset_acks: True`` — clear session acks (used by reopen).
    - ``reason: str`` — human-readable reason recorded to the audit log.
    - ``action: str`` — overrides ``action`` field on the audit record.
    """
    when = now or datetime.now(tz=timezone.utc)
    instance = instance_id or session_id
    if not instance:
        raise TransitionError("instance_id (or session_id) is required")

    spec = load_workflows(project_dir)
    workflow = _resolve_workflow(spec, workflow_id)
    statuses_by_id = workflow.statuses_by_id
    if target_status not in statuses_by_id:
        raise TransitionError(
            f"unknown status {target_status!r} in workflow {workflow_id!r}; "
            f"valid statuses: {sorted(statuses_by_id)}"
        )

    # Pre-lock load: just to populate `transition.requested`'s
    # `from_status` field with the caller's perspective. The gate
    # body re-loads inside the lock to evaluate against fresh state
    # (see codex P1 on PR #73 — concurrent transitions could otherwise
    # both validate against the same stale snapshot).
    try:
        pre_lock_session = load_session(project_dir, instance)
    except FileNotFoundError as exc:
        raise TransitionError(f"session {instance!r} not found") from exc

    pre_lock_status = pre_lock_session.status.value

    # Always emit `transition.requested` first.
    emit_event(
        project_dir,
        workflow=workflow_id,
        instance=instance,
        status=target_status,
        event="transition.requested",
        details={"from_status": pre_lock_status, "to_status": target_status},
        now=when,
    )

    lock_name = f".tripwire/locks/transition-{instance}.lock"
    try:
        with project_lock(project_dir, name=lock_name):
            # Re-read session state INSIDE the lock — stale snapshots
            # before the lock could let two concurrent transitions
            # validate against the same source status and both emit
            # `transition.completed`. Fresh read here is the
            # serialization point.
            session = load_session(project_dir, instance)
            current_status = session.status.value
            current = statuses_by_id.get(current_status)
            return _run_gate(
                project_dir,
                workflow_id=workflow_id,
                instance=instance,
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
            workflow=workflow_id,
            instance=instance,
            status=target_status,
            event="transition.rejected",
            details={"reason": result.reason, "message": result.message},
            now=datetime.now(tz=timezone.utc),
        )
        return result


def _run_gate(
    project_dir: Path,
    *,
    workflow_id: str,
    instance: str,
    session,
    workflow: Workflow,
    current,
    current_status: str,
    target_status: str,
    statuses_by_id: dict[str, WorkflowStatus],
    when: datetime,
    flags: dict,
) -> TransitionResult:
    """The gate body. Caller holds the per-instance transition lock."""
    # 1. Reachability.
    if current is None:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=f"transition_not_reachable: current status "
            f"{current_status!r} is not declared in workflow.yaml",
        )
    route = _route_between(workflow, current_status, target_status)
    if route is None:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=f"transition_not_reachable: cannot move from "
            f"{current_status!r} to {target_status!r} via declared workflow route",
        )

    target = statuses_by_id[target_status]
    controls = _controls_for_transition(route, target)

    # 2. Tripwires — target-status entry gate from workflow.yaml.
    #
    # Fail-loud on unknown validator ids: the load-time
    # `workflow/unknown_tripwire` lint already catches typos at load,
    # but if the catalog drifts from the workflow.yaml between load and
    # transition (e.g. a validator was deleted in code while the YAML
    # still references it), `validate_project` would silently skip the
    # missing id and the gate would pass against fewer checks than the
    # route declared. Surface that as a structured rejection here so
    # the gate is honest about which tripwires actually ran.
    from tripwire.cli.transition import validate_project
    from tripwire.core.workflow.registry import validator_catalog

    catalog_ids = set(validator_catalog())
    unknown_tripwires = [tid for tid in controls.tripwires if tid not in catalog_ids]
    if unknown_tripwires:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=(
                f"unknown_tripwire: route declares validator id(s) "
                f"{sorted(unknown_tripwires)} that are not registered in "
                f"the validator catalog — refusing to run a partial gate"
            ),
        )

    report = validate_project(
        project_dir,
        strict=True,
        fix=False,
        session_id=instance,
        validator_ids=controls.tripwires,
        workflow=workflow_id,
        status=target_status,
    )
    if report.errors:
        first = report.errors[0]
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=f"tripwires_failed: {first.code}: {first.message}",
        )

    # 3. JIT prompts — target-status entry gate from workflow.yaml.
    jit_prompt_ids = list(controls.jit_prompts)
    if jit_prompt_ids:
        from tripwire._internal.jit_prompts.loader import load_jit_prompt_registry

        registry = load_jit_prompt_registry(project_dir)
        unacked = _unacked_status_jit_prompts(
            project_dir, registry, session_id=instance, want_ids=set(jit_prompt_ids)
        )
        if unacked:
            return _reject(
                project_dir,
                workflow_id,
                instance,
                target_status,
                reason=f"jit_prompts_not_acknowledged: {sorted(unacked)}",
            )

    # 4. Prompt-checks — target-status entry gate from workflow.yaml.
    required_pcs = list(controls.prompt_checks)
    if required_pcs:
        invoked = _invoked_prompt_checks_at_status(
            project_dir, instance=instance, status=target_status
        )
        missing = [pc for pc in required_pcs if pc not in invoked]
        if missing:
            return _reject(
                project_dir,
                workflow_id,
                instance,
                target_status,
                reason=f"prompt_checks_missing: {missing}",
            )

    # 5. Artifacts — target-status consumed paths must exist.
    missing_artifacts = _missing_consumed_artifacts(
        project_dir,
        session_id=instance,
        target=target,
        session=session,
    )
    if missing_artifacts:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=f"artifacts_missing: {missing_artifacts}",
        )

    # 6. Capture pre-state for preserve/clear semantics.
    preserved: dict[str, object] = {
        path: _read_path(session, path) for path in route.preserve_fields
    }
    for path in route.clear_fields:
        _write_path(session, path, None)

    # 7. Flip status, assign status-instance id, save.
    n = _next_status_instance_n(project_dir, workflow_id, instance, target_status)
    status_instance = f"{workflow_id}:{instance}:{target_status}:{n}"
    session.status = SessionStatus(target_status)
    session.current_status_instance = status_instance
    session.updated_at = when

    # 8. Re-assert preserved fields against accidental clearing.
    for path, prior_value in preserved.items():
        current_value = _read_path(session, path)
        if current_value != prior_value:
            _write_path(session, path, prior_value)
    save_session(project_dir, session)

    # 9. Best-effort post-write hooks. None of these may roll back the
    #    transition — the status write above is the commit point. Each
    #    is wrapped to swallow exceptions so housekeeping never blocks.
    if workflow_id == "coding-session":
        _apply_post_write_hooks(
            project_dir,
            session=session,
            route=route,
            from_status=current_status,
            flags=flags,
            when=when,
        )

    # 10. Emit transition.completed.
    emit_event(
        project_dir,
        workflow=workflow_id,
        instance=instance,
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


def _apply_post_write_hooks(
    project_dir: Path,
    *,
    session: AgentSession,
    route: WorkflowRoute,
    from_status: str,
    flags: dict,
    when: datetime,
) -> None:
    """Run the four inline best-effort hooks after the status flip.

    Order is fixed: close engagement, audit, telemetry, reset acks.
    ``close_active_engagement`` must run before ``append_telemetry``
    so duration_min derives from a closed engagement on terminal
    transitions. Any exception is caught and logged — housekeeping
    failures never roll back the (already-committed) status write.
    """
    from tripwire.core.workflow.side_effects import (
        append_audit_record,
        append_telemetry_record,
        close_active_engagement,
        reset_acks_if_requested,
    )

    try:
        engagement_modified = close_active_engagement(session, route, now=when)
        if engagement_modified:
            save_session(project_dir, session)
    except Exception:
        logger.exception(
            "post-write hook close_active_engagement failed for session %s",
            session.id,
        )

    try:
        append_audit_record(
            project_dir,
            session=session,
            route=route,
            from_status=from_status,
            flags=flags,
            now=when,
        )
    except Exception:
        logger.exception(
            "post-write hook append_audit_record failed for session %s", session.id
        )

    try:
        append_telemetry_record(project_dir, session=session)
    except Exception:
        logger.exception(
            "post-write hook append_telemetry_record failed for session %s",
            session.id,
        )

    try:
        reset_acks_if_requested(project_dir, session=session, flags=flags)
    except Exception:
        logger.exception(
            "post-write hook reset_acks_if_requested failed for session %s",
            session.id,
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
    workflow_id: str,
    instance: str,
    target_status: str,
    *,
    reason: str,
) -> TransitionResult:
    emit_event(
        project_dir,
        workflow=workflow_id,
        instance=instance,
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
    "TransitionError",
    "TransitionResult",
    "execute_transition",
]
