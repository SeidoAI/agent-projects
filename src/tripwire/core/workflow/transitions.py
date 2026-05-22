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
6. Flips the instance's status field, bumps ``current_status_instance``,
   saves the instance. The coding-session workflow round-trips through
   the typed :class:`AgentSession` model; every other workflow round-
   trips through the generic dict loader/saver in :mod:`instance_io`.
7. Runs four best-effort post-write hooks inline. Each is guarded to
   no-op gracefully for non-coding-session instances (engagement close
   requires ``engagements``; telemetry requires session cost tracking):
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

Concurrency: per-(workflow, instance) lockfile under
``.tripwire/locks/transition-<workflow>-<instance>.lock`` serialises
concurrent transitions on the same entity — the execute path is the
single serialization point for ``session.status`` mutations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tripwire.core import paths
from tripwire.core.events.log import emit_event, isoformat_z, read_events
from tripwire.core.locks import LockTimeout, project_lock
from tripwire.core.session_store import load_session, save_session
from tripwire.core.workflow.instance_io import (
    InstanceNotFoundError,
    WorkflowMissingInstanceBlockError,
    load_instance,
    save_instance,
)
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

# The single workflow id that materialises as a typed pydantic model
# (``AgentSession``). Every other workflow id flows through the generic
# dict-based instance loader. Centralised here so the dispatch sites
# below read the same constant.
_CODING_SESSION_WORKFLOW_ID = "coding-session"


def _load_workflow_instance(
    project_dir: Path,
    workflow_id: str,
    instance_id: str,
    *,
    workflow: Workflow | None = None,
) -> Any:
    """Load an instance for *workflow_id*.

    Dispatches on the workflow id: ``coding-session`` returns the typed
    :class:`AgentSession` via :func:`load_session`; every other workflow
    returns a plain dict via :func:`load_instance`. The caller uses
    :func:`_get_status` / :func:`_set_status` to read/write the status
    field uniformly across both shapes.

    *workflow* is the pre-resolved :class:`Workflow` (the executor parses
    ``workflow.yaml`` once at the top of :func:`execute_transition` and
    threads the result here). When provided the generic dict loader
    skips its internal :func:`load_workflows` call — the executor's two
    instance loads per transition (pre-lock + in-lock) thus reuse the
    single parse.

    Raises :class:`TransitionError` for missing instance files so the
    legacy "session not found" error contract is preserved for the
    coding-session path while non-coding-session callers see a parallel
    structured error.
    """
    if workflow_id == _CODING_SESSION_WORKFLOW_ID:
        try:
            return load_session(project_dir, instance_id)
        except FileNotFoundError as exc:
            raise TransitionError(f"session {instance_id!r} not found") from exc
    try:
        return load_instance(project_dir, workflow_id, instance_id, workflow=workflow)
    except InstanceNotFoundError as exc:
        raise TransitionError(
            f"instance {instance_id!r} for workflow {workflow_id!r} not found"
        ) from exc
    except WorkflowMissingInstanceBlockError as exc:
        # The workflow exists but its `instance:` block was never
        # declared, so the generic loader has no storage_path to resolve.
        # Surface as a transition error so the gate fails loud rather
        # than silently routing to a fallback path.
        raise TransitionError(str(exc)) from exc


def _save_workflow_instance(
    project_dir: Path,
    workflow_id: str,
    instance_id: str,
    obj: Any,
    *,
    workflow: Workflow | None = None,
) -> None:
    """Persist an instance loaded by :func:`_load_workflow_instance`.

    Mirror of the loader: ``coding-session`` round-trips through the
    typed :func:`save_session`, every other workflow round-trips through
    the generic :func:`save_instance` (writes the dict back to its
    declared ``storage_path``). Pass *workflow* to skip the redundant
    ``workflow.yaml`` parse — see :func:`_load_workflow_instance`.
    """
    if workflow_id == _CODING_SESSION_WORKFLOW_ID:
        save_session(project_dir, obj)
    else:
        save_instance(project_dir, workflow_id, instance_id, obj, workflow=workflow)


def _get_status(obj: Any, workflow: Workflow) -> str:
    """Read the current status from a typed model or a dict.

    The workflow's ``instance.status_field`` names the field; for the
    coding-session path the typed ``AgentSession`` returns a
    :class:`SessionStatus` enum (``StrEnum``) which we coerce to its
    string value for uniform comparison against ``statuses_by_id``.
    Workflows without an ``instance:`` block default the field name to
    ``status`` (only the coding-session bootstrap fixture hits this in
    tests today; production workflows declare the block).
    """
    field_name = workflow.instance.status_field if workflow.instance else "status"
    if isinstance(obj, dict):
        value = obj.get(field_name, "")
        return value if isinstance(value, str) else str(value)
    value = getattr(obj, field_name, "")
    # StrEnum values render as their string value via ``.value``; fall
    # back to ``str()`` so plain strings flow through unchanged.
    return getattr(value, "value", value) if value is not None else ""


def _set_status(obj: Any, workflow: Workflow, value: str) -> None:
    """Write the status field on a typed model or a dict.

    For dicts we write the raw string verbatim — the generic instance
    loader does no enum coercion. For typed ``AgentSession`` we wrap in
    :class:`SessionStatus` to match the model's declared type (pydantic
    would coerce strings too, but the explicit enum keeps existing
    behaviour bit-identical).
    """
    field_name = workflow.instance.status_field if workflow.instance else "status"
    if isinstance(obj, dict):
        obj[field_name] = value
        return
    if field_name == "status" and isinstance(obj, AgentSession):
        setattr(obj, field_name, SessionStatus(value))
    else:
        setattr(obj, field_name, value)


def _maybe_close_active_engagement(
    instance: Any, route: WorkflowRoute, *, now: datetime
) -> bool:
    """Run :func:`close_active_engagement` only when the instance is a
    coding-session — i.e. has the ``engagements`` attribute. Returns the
    underlying modified flag, or False for instances without engagements
    (the hook is a no-op for issue/project/etc. instances).
    """
    if not hasattr(instance, "engagements"):
        return False
    from tripwire.core.workflow.post_write_hooks import close_active_engagement

    return close_active_engagement(instance, route, now=now)


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of one transition request."""

    ok: bool
    reason: str | None  # structured reason code; None on pass
    message: str | None  # human-readable detail
    status_instance: str | None  # `{workflow}:{instance}:{status}:{n}` on pass


class TransitionError(Exception):
    """Raised for unrecoverable input errors (unknown session/status).

    Also raised by ``_run_declared_side_effects`` when a side-effect
    script exits non-zero; ``execute_transition`` catches it and
    translates to a ``transition.rejected`` event with the script's
    failure reason. Status is not flipped on rejection.
    """


def _run_declared_side_effects(
    project_dir: Path,
    *,
    workflow_id: str,
    instance_id: str,
    route: WorkflowRoute,
) -> None:
    """Invoke each declared side_effect script in order, synchronously.

    v0.14.0 — each name in ``route.side_effects`` maps to a Python
    script at ``templates/side_effects/<entity>/<name>.py`` (overridable
    per project at ``<project>/.tripwire/side_effects/<entity>/<name>.py``).
    The ``<entity>`` subdir is resolved from ``workflow_id`` via
    :data:`tripwire.core.paths._WORKFLOW_ENTITY_DIR`.
    Scripts run via ``subprocess.run([sys.executable, script_path,
    ...])`` with the executor's own stderr inherited so progress
    reaches the agent's transcript inline (no opt-in explain flag —
    progressive disclosure is unconditional).

    Contract: exit code 0 = success, continue. Non-zero = failure —
    raise :class:`TransitionError` with the script name + exit code
    so ``execute_transition`` aborts BEFORE the status write. The
    status flip downstream is the certificate that every validator
    AND every side_effect passed.

    Each script receives:
      --project-dir <path>
      --session-id  <instance-id>
      --from-status <route.from_ref>
      --to-status   <route.to_ref>

    Scripts that don't use the status args accept-and-ignore them
    (uniform interface across all 8 shipped scripts).
    """
    if not route.side_effects:
        return

    import subprocess
    import sys

    from tripwire.core.paths import resolve_side_effect_path

    for name in route.side_effects:
        script_path = resolve_side_effect_path(
            project_dir, name, workflow_id=workflow_id
        )
        if not script_path.is_file():
            raise TransitionError(
                f"side_effect/script_not_found: declared side_effect "
                f"{name!r} on route {workflow_id}/{route.id} resolves to "
                f"{script_path} which does not exist on disk."
            )

        print(
            f"running side_effects/{name}.py for {workflow_id}/{instance_id}...",
            file=sys.stderr,
        )
        result = subprocess.run(
            [
                sys.executable,
                str(script_path),
                "--project-dir",
                str(project_dir),
                "--session-id",
                instance_id,
                "--from-status",
                route.from_ref,
                "--to-status",
                route.to_ref,
            ],
            stderr=sys.stderr,
        )
        if result.returncode != 0:
            raise TransitionError(
                f"side_effect/failed: {name!r} exited with code "
                f"{result.returncode}. transition aborted; status "
                f"unchanged. fix the underlying state and re-run the "
                f"transition, or invoke `templates/side_effects/{name}.py` "
                f"directly to debug."
            )


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
    ``coding-session`` round-trips through the typed
    :class:`AgentSession` model; every other declared workflow flows
    through the generic dict loader in
    :mod:`tripwire.core.workflow.instance_io`. Unknown workflow ids
    still raise :class:`TransitionError` at load.

    ``instance_id`` (or the legacy positional ``session_id``) names the
    entity being transitioned. For the coding-session workflow this is
    the session id; for other workflows it is whatever the workflow's
    ``instance.storage_path`` template renders against (issue key,
    project name, etc.).

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
    # both validate against the same stale snapshot). Pass the
    # pre-resolved workflow so the generic dict loader skips re-parsing
    # ``workflow.yaml``.
    pre_lock_instance = _load_workflow_instance(
        project_dir, workflow_id, instance, workflow=workflow
    )
    pre_lock_status = _get_status(pre_lock_instance, workflow)

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

    lock_path = paths.transition_lock_path(project_dir, workflow_id, instance)
    lock_name = str(lock_path.relative_to(project_dir))
    try:
        with project_lock(project_dir, name=lock_name):
            # Re-read instance state INSIDE the lock — stale snapshots
            # before the lock could let two concurrent transitions
            # validate against the same source status and both emit
            # `transition.completed`. Fresh read here is the
            # serialization point. The pre-resolved workflow is still
            # the right shape: workflow.yaml does not change mid-
            # transition (per-instance lock has no bearing on the
            # workflow file), so re-parsing it would be pure waste.
            instance_obj = _load_workflow_instance(
                project_dir, workflow_id, instance, workflow=workflow
            )
            current_status = _get_status(instance_obj, workflow)
            current = statuses_by_id.get(current_status)
            return _run_gate(
                project_dir,
                workflow_id=workflow_id,
                instance=instance,
                session=instance_obj,
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
    # v0.13.2 #4: the session-lifecycle validators iterate
    # ``ctx.sessions`` unfiltered, so a finding against session A
    # (e.g. its PR isn't merged) would block transitioning session B.
    # Scope the report to findings against the target instance and its
    # members (for ``coding-session``, the session's member issues)
    # before checking errors. Project-level findings (no `file`) pass
    # through. The member-scope expansion is the codex-HIGH fix on top
    # of the original v0.13.2 #4: without it, an unverified member
    # issue would never block the session's transition to ``completed``.
    in_scope = _in_scope_instance_ids(project_dir, workflow_id, instance)
    _filter_report_to_target_instance(report, in_scope)
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

    # 5. Artifacts — target-status consumed paths must exist. The
    # artifact resolver reads ``session.issues`` for the ``{issue_key}``
    # placeholder, which only exists on typed AgentSession. For
    # dict-backed instances we skip the issues-derived context — the
    # workflow's declared artifacts for those instances either don't
    # use the placeholder or settle at write-time.
    artifact_owner = session if isinstance(session, AgentSession) else None
    missing_artifacts = _missing_consumed_artifacts(
        project_dir,
        session_id=instance,
        target=target,
        session=artifact_owner,
    )
    if missing_artifacts:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=f"artifacts_missing: {missing_artifacts}",
        )

    # 6. Run declared side_effects as standalone scripts (v0.14.0).
    #    Each name in route.side_effects maps to a file under
    #    ``templates/side_effects/<name>.py`` (override at
    #    ``<project>/.tripwire/side_effects/<name>.py``). Scripts run
    #    synchronously via subprocess BEFORE the status flip; any
    #    non-zero exit aborts the transition with status unchanged.
    #    The status flip below is therefore the certificate that every
    #    validator AND every side_effect passed — no post-conditions
    #    or recovery layer.
    try:
        _run_declared_side_effects(
            project_dir,
            workflow_id=workflow_id,
            instance_id=instance,
            route=route,
        )
    except TransitionError as exc:
        return _reject(
            project_dir,
            workflow_id,
            instance,
            target_status,
            reason=str(exc),
        )

    # 7. Capture pre-state for preserve/clear semantics. Only the
    # coding-session model declares these fields today (dotted paths
    # against ``AgentSession``); guarding the whole block keeps the
    # dict-loader path simple and avoids inventing dotted-path
    # semantics on dicts for a feature no other workflow uses yet.
    is_coding_session = workflow_id == _CODING_SESSION_WORKFLOW_ID
    preserved: dict[str, object] = {}
    if is_coding_session:
        preserved = {path: _read_path(session, path) for path in route.preserve_fields}
        for path in route.clear_fields:
            _write_path(session, path, None)

    # 8. Flip status, assign status-instance id, save. This is the
    # commit point — every validator and every declared side_effect
    # has passed by this line.
    n = _next_status_instance_n(project_dir, workflow_id, instance, target_status)
    status_instance = f"{workflow_id}:{instance}:{target_status}:{n}"
    _set_status(session, workflow, target_status)
    if isinstance(session, dict):
        session["current_status_instance"] = status_instance
        # ``updated_at`` is conventional but optional on dict instances —
        # write an ISO string so YAML round-trips cleanly.
        session["updated_at"] = isoformat_z(when)
    else:
        session.current_status_instance = status_instance
        session.updated_at = when

    # 8. Re-assert preserved fields against accidental clearing.
    if is_coding_session:
        for path, prior_value in preserved.items():
            current_value = _read_path(session, path)
            if current_value != prior_value:
                _write_path(session, path, prior_value)
    _save_workflow_instance(
        project_dir, workflow_id, instance, session, workflow=workflow
    )

    # 9. Best-effort post-write hooks. None of these may roll back the
    #    transition — the status write above is the commit point. Each
    #    is wrapped to swallow exceptions so housekeeping never blocks.
    _apply_post_write_hooks(
        project_dir,
        workflow_id=workflow_id,
        instance_id=instance,
        instance_obj=session,
        workflow=workflow,
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
    workflow_id: str,
    instance_id: str,
    instance_obj: Any,
    workflow: Workflow,
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

    Per-hook coding-session-ness:

    - ``close_active_engagement`` requires ``instance_obj.engagements``;
      guarded via :func:`_maybe_close_active_engagement` (no-op for
      dict-backed instances that have no engagement tracking).
    - ``append_audit_record`` and ``append_telemetry_record`` read
      session-specific fields (``session.id``, ``compute_session_cost``)
      that don't exist on other instances; both are scoped to the
      coding-session path. Other workflows get their own audit trail via
      ``transition.completed`` events on the standard events log.
    - ``reset_acks_if_requested`` is a coding-session-only flag (the
      reopen route sets it); guarded with the same workflow-id check
      since it reaches into per-session ack files.
    """
    from tripwire.core.workflow.post_write_hooks import (
        append_audit_record,
        append_telemetry_record,
        reset_acks_if_requested,
    )

    is_coding_session = workflow_id == _CODING_SESSION_WORKFLOW_ID

    try:
        engagement_modified = _maybe_close_active_engagement(
            instance_obj, route, now=when
        )
        if engagement_modified:
            _save_workflow_instance(
                project_dir,
                workflow_id,
                instance_id,
                instance_obj,
                workflow=workflow,
            )
    except Exception:
        logger.exception(
            "post-write hook close_active_engagement failed for instance %s",
            instance_id,
        )

    if is_coding_session:
        try:
            append_audit_record(
                project_dir,
                session=instance_obj,
                route=route,
                from_status=from_status,
                flags=flags,
                now=when,
            )
        except Exception:
            logger.exception(
                "post-write hook append_audit_record failed for session %s",
                instance_id,
            )

        # Telemetry records one row per session-COMPLETION, not per
        # transition. Without this gate every coding-session writes
        # ~5 rows (planned→queued→…→completed) and
        # `queue_runner._recent_spend_usd` sums ~Nx actual spend,
        # tripping false `cap_usd_per_window` rejections; analyze-
        # routing's $/merged-PR is similarly inflated.
        # See v0.13.2 finding #3.
        if route.to_ref == "completed":
            try:
                append_telemetry_record(project_dir, session=instance_obj)
            except Exception:
                logger.exception(
                    "post-write hook append_telemetry_record failed for session %s",
                    instance_id,
                )

        try:
            reset_acks_if_requested(project_dir, session=instance_obj, flags=flags)
        except Exception:
            logger.exception(
                "post-write hook reset_acks_if_requested failed for session %s",
                instance_id,
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


def _instance_owner_from_path(file_path: str) -> str | None:
    """Extract the owning instance id from a finding's file path.

    Returns the id segment of ``instances/<type>/<id>/...`` (subdir
    layout) or the stem of ``instances/<type>/<id>.yaml`` (flat layout).
    Returns ``None`` for paths that don't fit either shape (project-
    level findings, ``workflow.yaml``, etc.) — callers treat those as
    project-level and let them pass through scope filtering.
    """
    parts = Path(file_path).parts
    if len(parts) >= 3 and parts[0] == "instances":
        # instances/<type>/<rest>...
        # Subdir layout: instances/sessions/<sid>/session.yaml → "sessions", "<sid>", ...
        # Flat layout:   instances/nodes/<id>.yaml             → "nodes", "<id>.yaml"
        third = parts[2]
        if third.endswith(".yaml"):
            return third[: -len(".yaml")]
        return third
    return None


def _in_scope_instance_ids(
    project_dir: Path, workflow_id: str, instance: str
) -> set[str]:
    """Return the set of instance ids whose findings should still
    block transitioning ``instance``.

    Always includes ``instance`` itself. For ``coding-session``, also
    includes the session's member issue keys: a finding against one of
    the session's own issues (e.g. an unverified KUI-123) is a legitimate
    blocker for transitioning the session to ``completed``. Without this
    expansion the v0.13.2 #4 scope filter over-cropped and silently let
    member-issue failures through.

    Failure to load the session (missing file, broken yaml) falls back to
    ``{instance}`` only — the instance-shape validator surfaces the load
    failure through its own finding, which still belongs to ``instance``.
    """
    in_scope: set[str] = {instance}
    if workflow_id == "coding-session":
        try:
            from tripwire.core.session_store import load_session

            session = load_session(project_dir, instance)
        except Exception:
            return in_scope
        for issue_key in getattr(session, "issues", []) or []:
            in_scope.add(issue_key)
    return in_scope


def _filter_report_to_target_instance(report, in_scope: set[str]) -> None:
    """In-place scope a validation report to the target transition's
    instance and its members.

    Per-instance tripwires (the session-lifecycle catalog, primarily)
    iterate every entity in the project. Without scoping, a finding
    against session A blocks transitioning session B. This filter drops
    findings whose owning instance is outside ``in_scope`` — the set is
    typically ``{target} | <member instance ids>`` so legitimate member
    blockers survive the filter.

    Project-level findings (no ``file``) and findings against entities
    we can't attribute to an owner pass through — they represent
    invariants the whole project owes, not per-instance state.
    """

    def _keep(finding) -> bool:
        if not finding.file:
            return True
        owner = _instance_owner_from_path(finding.file)
        if owner is None:
            return True
        return owner in in_scope

    report.errors = [f for f in report.errors if _keep(f)]
    report.warnings = [f for f in report.warnings if _keep(f)]
    report.fixed = [f for f in report.fixed if _keep(f)]
    # Recompute exit code to reflect filtered errors.
    if report.errors:
        report.exit_code = 2
    elif report.warnings:
        report.exit_code = 1
    else:
        report.exit_code = 0


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
